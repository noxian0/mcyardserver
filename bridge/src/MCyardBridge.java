package dev.mcyard.bridge;

import com.google.gson.*;
import com.mojang.serialization.JsonOps;
import net.fabricmc.api.ModInitializer;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerLifecycleEvents;
import net.fabricmc.fabric.api.event.lifecycle.v1.ServerTickEvents;
import net.fabricmc.fabric.api.entity.event.v1.ServerLivingEntityEvents;
import net.fabricmc.fabric.api.entity.event.v1.ServerPlayerEvents;
import net.fabricmc.fabric.api.networking.v1.ServerPlayConnectionEvents;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.item.ItemStack;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.RegistryOps;
import net.minecraft.world.level.storage.LevelData;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** Local-files-only admin bridge. No listeners, remote ports or client mods. */
public final class MCyardBridge implements ModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("mcyard-bridge");
    private static final Gson JSON = new Gson();
    private final Path dir = Path.of("manager", "data");
    private final String session = UUID.randomUUID().toString();
    private final Map<UUID,String> modes = new HashMap<>(), spawns = new HashMap<>();
    private record Anchor(ServerLevel level,double x,double y,double z) {}
    private final Map<UUID,Anchor> frozen = new HashMap<>();
    private final LinkedHashMap<String,JsonObject> completedActions = new LinkedHashMap<>();
    private final ExecutorService writer = Executors.newSingleThreadExecutor(r -> new Thread(r,"MCyard Server-Writer"));
    private final ScheduledExecutorService poller = Executors.newSingleThreadScheduledExecutor(r -> new Thread(r,"MCyard Server-Poller"));
    private final AtomicBoolean pending = new AtomicBoolean();
    private volatile boolean active;
    private long started;

    public void onInitialize() {
        try { Files.createDirectories(dir.resolve("inbox")); Files.createDirectories(dir.resolve("replies")); Files.createDirectories(dir.resolve("players")); }
        catch (Exception e) { throw new RuntimeException("Cannot initialize local manager files", e); }
        ServerLifecycleEvents.SERVER_STARTED.register(server -> {
            started = System.currentTimeMillis(); active = true;
            event(null,"server_start","Server started",null);
            poller.scheduleWithFixedDelay(() -> {
                if (active && pending.compareAndSet(false,true)) server.execute(() -> {
                    try { commands(server); if(active) snapshot(server); }
                    catch (Exception e) { LOG.error("Manager update failed",e); }
                    finally { pending.set(false); }
                });
            },0,2,TimeUnit.SECONDS);
        });
        ServerTickEvents.END_SERVER_TICK.register(server -> {
            for (ServerPlayer p : server.getPlayerList().getPlayers()) {
                enforceFrozen(p);
                String mode = p.gameMode().getName(), old = modes.put(p.getUUID(),mode);
                if (old != null && !old.equals(mode)) event(p,"gamemode",old+" \u2192 "+mode,null);
                String spawn = spawn(p,server).toString(), prev = spawns.put(p.getUUID(),spawn);
                if (prev != null && !prev.equals(spawn)) event(p,"spawnpoint","Respawn point changed",spawn(p,server));
            }
        });
        ServerPlayConnectionEvents.JOIN.register((handler,sender,server) -> {
            ServerPlayer p=handler.player;
            event(p,"join","Joined from "+p.getIpAddress(),null);
            event(p,"gamemode_observed","Joined in "+p.gameMode().getName(),null);
        });
        ServerPlayConnectionEvents.DISCONNECT.register((handler,server) -> {
            ServerPlayer p=handler.player; thaw(p,"Disconnected"); persist(p,server); event(p,"leave","Disconnected",null);
            modes.remove(p.getUUID()); spawns.remove(p.getUUID());
        });
        ServerLivingEntityEvents.AFTER_DEATH.register((entity,source) -> {
            if (entity instanceof ServerPlayer p) { thaw(p,"Player died"); event(p,"death",source.getLocalizedDeathMessage(p).getString(),location(p)); }
        });
        ServerPlayerEvents.AFTER_RESPAWN.register((oldPlayer,newPlayer,alive) -> { thaw(newPlayer,"Player respawned"); event(newPlayer,"respawn","Respawned",location(newPlayer)); });
        ServerLifecycleEvents.SERVER_STOPPING.register(server -> {
            active=false; poller.shutdownNow();
            for (ServerPlayer p:server.getPlayerList().getPlayers()) thaw(p,"Server stopping");
            frozen.clear(); completedActions.clear();
            for (ServerPlayer p:server.getPlayerList().getPlayers()) persist(p,server);
            event(null,"server_stop","Server stopping",null);
            JsonObject stopped=new JsonObject(); stopped.addProperty("online",false); stopped.addProperty("time",System.currentTimeMillis()); stopped.addProperty("session",session);
            stopped.add("world",world(server));
            write(dir.resolve("status.json"),stopped);
        });
        ServerLifecycleEvents.SERVER_STOPPED.register(server -> {
            writer.shutdown(); try { writer.awaitTermination(10,TimeUnit.SECONDS); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
        });
        LOG.info("MCyard Server bridge ready (local files only)");
    }

    private JsonObject location(ServerPlayer p) {
        JsonObject o=new JsonObject(); o.addProperty("dimension",p.level().dimension().identifier().toString());
        o.addProperty("x",p.getX()); o.addProperty("y",p.getY()); o.addProperty("z",p.getZ()); return o;
    }
    private JsonObject spawn(ServerPlayer p,MinecraftServer server) {
        var config=p.getRespawnConfig(); LevelData.RespawnData data=config==null?server.getRespawnData():config.respawnData();
        JsonObject o=new JsonObject(); o.addProperty("dimension",data.dimension().identifier().toString());
        o.addProperty("x",data.pos().getX()); o.addProperty("y",data.pos().getY()); o.addProperty("z",data.pos().getZ());
        o.addProperty("source",config==null?"World spawn":"Personal respawn point"); return o;
    }
    private JsonObject item(ItemStack stack,String slot,MinecraftServer server) {
        JsonObject o=new JsonObject(); o.addProperty("slot",slot);
        o.addProperty("id",BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());
        o.addProperty("name",stack.getHoverName().getString()); o.addProperty("count",stack.getCount());
        o.addProperty("damage",stack.getDamageValue()); o.addProperty("maxDamage",stack.getMaxDamage());
        ItemStack.CODEC.encodeStart(RegistryOps.create(JsonOps.INSTANCE,server.registryAccess()),stack).result().ifPresent(v -> {
            o.add("data",v); o.addProperty("revision",revision(v));
        });
        return o;
    }
    private JsonObject player(ServerPlayer p,MinecraftServer server) {
        JsonObject o=new JsonObject(); o.addProperty("uuid",p.getUUID().toString()); o.addProperty("name",p.getPlainTextName());
        o.addProperty("ip",p.getIpAddress()); o.addProperty("mode",p.gameMode().getName());
        o.addProperty("health",p.getHealth()); o.addProperty("food",p.getFoodData().getFoodLevel());
        o.addProperty("xp",p.experienceLevel); o.addProperty("op",server.getPlayerList().isOp(p.nameAndId()));
        o.addProperty("frozen",frozen.containsKey(p.getUUID()));
        o.addProperty("time",System.currentTimeMillis()); o.add("position",location(p)); o.add("spawn",spawn(p,server));
        p.getLastDeathLocation().ifPresent(pos -> {
            JsonObject d=new JsonObject(); d.addProperty("dimension",pos.dimension().identifier().toString());
            d.addProperty("x",pos.pos().getX()); d.addProperty("y",pos.pos().getY()); d.addProperty("z",pos.pos().getZ()); o.add("lastDeath",d);
        });
        JsonArray inventory=new JsonArray(),ender=new JsonArray();
        for(int i=0;i<36;i++) { var s=p.getInventory().getItem(i); if(!s.isEmpty()) inventory.add(item(s,Integer.toString(i),server)); }
        for(var slot:List.of(EquipmentSlot.HEAD,EquipmentSlot.CHEST,EquipmentSlot.LEGS,EquipmentSlot.FEET,EquipmentSlot.OFFHAND)) {
            var s=p.getItemBySlot(slot); if(!s.isEmpty()) inventory.add(item(s,slot.getName(),server));
        }
        for(int i=0;i<p.getEnderChestInventory().getContainerSize();i++) { var s=p.getEnderChestInventory().getItem(i); if(!s.isEmpty()) ender.add(item(s,Integer.toString(i),server)); }
        o.add("inventory",inventory); o.add("ender",ender); return o;
    }
    private void persist(ServerPlayer p,MinecraftServer server) { write(dir.resolve("players").resolve(p.getUUID()+".json"),player(p,server)); }
    private JsonObject world(MinecraftServer server) {
        var level=server.overworld();
        JsonObject world=new JsonObject();
        world.addProperty("dayTime",Math.floorMod(level.getOverworldClockTime(),24000L));
        world.addProperty("raining",level.isRaining());
        world.addProperty("thundering",level.isThundering());
        return world;
    }
    private void snapshot(MinecraftServer server) {
        JsonObject o=new JsonObject(); o.addProperty("online",true); o.addProperty("session",session); o.addProperty("time",System.currentTimeMillis());
        o.addProperty("pid",ProcessHandle.current().pid()); o.addProperty("started",started);
        o.addProperty("mspt",server.getAverageTickTimeNanos()/1000000.0); o.addProperty("maxPlayers",server.getPlayerList().getMaxPlayers());
        var runtime=Runtime.getRuntime(); o.addProperty("memoryUsed",runtime.totalMemory()-runtime.freeMemory()); o.addProperty("memoryMax",runtime.maxMemory());
        o.addProperty("version",server.getServerVersion());
        o.add("world",world(server));
        JsonObject features=new JsonObject(); features.addProperty("inventoryTransfer",true); features.addProperty("freezePlayer",true); o.add("features",features);
        JsonArray players=new JsonArray();
        for(ServerPlayer p:server.getPlayerList().getPlayers()) { var data=player(p,server); players.add(data); write(dir.resolve("players").resolve(p.getUUID()+".json"),data); }
        o.add("players",players);
        JsonObject rules=new JsonObject(); server.getGameRules().availableRules().forEach(rule -> {
            JsonObject r=new JsonObject(); r.addProperty("value",server.getGameRules().getAsString(rule));
            r.addProperty("type",rule.valueClass()==Boolean.class?"bool":"int"); rules.add(rule.id(),r);
        }); o.add("rules",rules); write(dir.resolve("rules.json"),rules); write(dir.resolve("status.json"),o);
    }
    private void event(ServerPlayer p,String type,String text,JsonObject detail) {
        JsonObject o=new JsonObject(); o.addProperty("id",UUID.randomUUID().toString()); o.addProperty("time",System.currentTimeMillis());
        o.addProperty("type",type); o.addProperty("text",text);
        if(p!=null) { o.addProperty("uuid",p.getUUID().toString()); o.addProperty("name",p.getPlainTextName()); o.add("position",location(p)); }
        if(detail!=null) o.add("detail",detail);
        String line=JSON.toJson(o)+"\n";
        writer.submit(() -> { try { Files.writeString(dir.resolve("events-"+java.time.LocalDate.now()+".jsonl"),line,StandardOpenOption.CREATE,StandardOpenOption.APPEND); }
            catch(Exception e) { LOG.error("Could not persist manager event",e); } });
    }
    private static JsonElement canonical(JsonElement value) {
        if (value.isJsonObject()) {
            JsonObject result=new JsonObject();
            new TreeMap<>(value.getAsJsonObject().asMap()).forEach((key,item)->result.add(key,canonical(item)));
            return result;
        }
        if (value.isJsonArray()) {
            JsonArray result=new JsonArray(); value.getAsJsonArray().forEach(item->result.add(canonical(item))); return result;
        }
        return value;
    }
    private static String revision(JsonElement data) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(JSON.toJson(canonical(data)).getBytes(StandardCharsets.UTF_8))); }
        catch (java.security.NoSuchAlgorithmException e) { throw new IllegalStateException("SHA-256 unavailable",e); }
    }
    private static String text(JsonObject value,String key,int max,boolean optional) {
        JsonElement element=value.get(key);
        if (element==null && optional) return "";
        if (element==null || !element.isJsonPrimitive() || !element.getAsJsonPrimitive().isString()) throw new IllegalArgumentException("Invalid "+key);
        String result=element.getAsString();
        if (result.length()>max || (!optional && result.isEmpty()) || result.chars().anyMatch(c->c<32 || c==127)) throw new IllegalArgumentException("Invalid "+key);
        return result;
    }
    private static int integer(JsonObject value,String key) {
        JsonElement element=value.get(key);
        if (element==null || !element.isJsonPrimitive() || !element.getAsJsonPrimitive().isNumber()) throw new IllegalArgumentException("Invalid "+key);
        try { return element.getAsBigDecimal().intValueExact(); }
        catch (ArithmeticException | NumberFormatException e) { throw new IllegalArgumentException("Invalid "+key); }
    }
    private static UUID playerId(JsonObject payload,String key) {
        String id=text(payload,key,36,false);
        if (!id.matches("[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")) throw new IllegalArgumentException("Invalid player UUID");
        return UUID.fromString(id);
    }
    private static ServerPlayer online(MinecraftServer server,UUID id) {
        ServerPlayer player=server.getPlayerList().getPlayer(id);
        if (player==null || !player.isAlive() || player.isRemoved()) throw new IllegalArgumentException("Both players must be online and alive. Refresh the player list.");
        return player;
    }
    private static void fields(JsonObject payload,Set<String> allowed) {
        if (!allowed.containsAll(payload.keySet())) throw new IllegalArgumentException("Unknown action field");
    }
    private record ItemSlot(ServerPlayer player,String kind,int index,EquipmentSlot equipment) {
        ItemStack get() {
            if (equipment!=null) return player.getItemBySlot(equipment);
            return kind.equals("ender") ? player.getEnderChestInventory().getItem(index) : player.getInventory().getItem(index);
        }
        void set(ItemStack stack) {
            if (equipment!=null) player.setItemSlot(equipment,stack);
            else if (kind.equals("ender")) player.getEnderChestInventory().setItem(index,stack);
            else player.getInventory().setItem(index,stack);
        }
    }
    private static ItemSlot sourceSlot(ServerPlayer player,String kind,String slot) {
        if (!kind.equals("inventory") && !kind.equals("ender")) throw new IllegalArgumentException("Choose inventory or Ender Chest.");
        if (slot.matches("0|[1-9][0-9]?")) {
            int index=Integer.parseInt(slot),limit=kind.equals("ender")?27:36;
            if (index>=limit) throw new IllegalArgumentException("Invalid inventory slot");
            return new ItemSlot(player,kind,index,null);
        }
        EquipmentSlot equipment=switch(slot) {
            case "head"->EquipmentSlot.HEAD; case "chest"->EquipmentSlot.CHEST; case "legs"->EquipmentSlot.LEGS;
            case "feet"->EquipmentSlot.FEET; case "offhand"->EquipmentSlot.OFFHAND; default->null;
        };
        if (!kind.equals("inventory") || equipment==null) throw new IllegalArgumentException("Invalid inventory slot");
        return new ItemSlot(player,kind,-1,equipment);
    }
    private static void syncInventory(ServerPlayer player) {
        player.getInventory().setChanged(); player.getEnderChestInventory().setChanged();
        player.inventoryMenu.broadcastChanges();
        if (player.containerMenu!=player.inventoryMenu) player.containerMenu.broadcastChanges();
    }
    private String transferItem(MinecraftServer server,JsonObject payload) {
        fields(payload,Set.of("source","target","kind","slot","count","expected","message"));
        UUID sourceId=playerId(payload,"source"),targetId=playerId(payload,"target");
        if (sourceId.equals(targetId)) throw new IllegalArgumentException("Choose a different receiving player.");
        String kind=text(payload,"kind",9,false),slot=text(payload,"slot",8,false),expected=text(payload,"expected",64,false);
        if (!expected.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("Refresh this item before transferring it.");
        String message=text(payload,"message",200,true).trim(); int count=integer(payload,"count");
        if (count<1 || count>999) throw new IllegalArgumentException("Invalid transfer quantity");
        ServerPlayer source=online(server,sourceId),target=online(server,targetId);
        ItemSlot origin=sourceSlot(source,kind,slot); ItemStack current=origin.get();
        if (current.isEmpty()) throw new IllegalArgumentException("That slot is now empty. Refresh the inventory.");
        JsonElement data=ItemStack.CODEC.encodeStart(RegistryOps.create(JsonOps.INSTANCE,server.registryAccess()),current).result()
            .orElseThrow(()->new IllegalArgumentException("This item cannot be transferred safely."));
        if (!expected.equals(revision(data))) throw new IllegalArgumentException("This item changed. Refresh the inventory and try again.");
        if (count>current.getCount()) throw new IllegalArgumentException("There are fewer items in this slot now. Refresh the inventory.");
        ItemStack original=current.copy(); ItemStack[] before=new ItemStack[36],after=new ItemStack[36];
        for (int i=0;i<36;i++) { before[i]=target.getInventory().getItem(i).copy(); after[i]=before[i].copy(); }
        int remaining=count;
        // Plan the entire transfer on copies before changing either real inventory.
        for (int i=0;i<36 && remaining>0;i++) {
            ItemStack destination=after[i];
            if (!destination.isEmpty() && ItemStack.isSameItemSameComponents(destination,original)) {
                int moved=Math.min(remaining,Math.max(0,target.getInventory().getMaxStackSize(destination)-destination.getCount()));
                if (moved>0) { after[i]=destination.copyWithCount(destination.getCount()+moved); remaining-=moved; }
            }
        }
        for (int i=0;i<36 && remaining>0;i++) if (after[i].isEmpty()) {
            int moved=Math.min(remaining,target.getInventory().getMaxStackSize(original));
            after[i]=original.copyWithCount(moved); remaining-=moved;
        }
        if (remaining!=0) throw new IllegalArgumentException("The receiving player's main inventory has too little space. Nothing was moved.");
        try {
            origin.set(count==original.getCount()?ItemStack.EMPTY:original.copyWithCount(original.getCount()-count));
            for (int i=0;i<36;i++) target.getInventory().setItem(i,after[i]);
        } catch (RuntimeException failure) {
            try {
                origin.set(original);
                for (int i=0;i<36;i++) target.getInventory().setItem(i,before[i]);
                syncInventory(source); syncInventory(target);
            } catch (RuntimeException rollback) {
                LOG.error("Inventory transfer rollback failed; inspect both inventories before retrying",rollback);
                throw new IllegalStateException("Transfer failed. Inspect both inventories and the server log before retrying.",failure);
            }
            throw new IllegalStateException("Transfer failed; both inventories were restored.",failure);
        }
        // The commit succeeded. Notification failures must never report a failed transfer.
        try { syncInventory(source); syncInventory(target); }
        catch (RuntimeException e) { LOG.error("Items transferred, but an inventory refresh failed",e); }
        String itemName=original.getHoverName().getString();
        String summary=count+" \u00d7 "+itemName;
        JsonObject detail=new JsonObject(); detail.addProperty("source",sourceId.toString()); detail.addProperty("target",targetId.toString());
        detail.addProperty("item",BuiltInRegistries.ITEM.getKey(original.getItem()).toString()); detail.addProperty("count",count);
        detail.addProperty("kind",kind); detail.addProperty("slot",slot); detail.addProperty("message",message);
        try {
            event(source,"item_transfer","Transferred "+summary+" to "+target.getPlainTextName(),detail);
            event(target,"item_transfer","Received "+summary+" from "+source.getPlainTextName(),detail);
        } catch (RuntimeException e) { LOG.error("Items transferred, but the local history could not be written",e); }
        if (!message.isEmpty()) {
            try { server.getPlayerList().broadcastSystemMessage(Component.literal("[MCyard] "+source.getPlainTextName()+" \u2192 "+target.getPlainTextName()+": "+summary+" \u2014 "+message),false); }
            catch (RuntimeException e) { LOG.error("Items transferred, but the optional chat notification failed",e); }
        }
        return "Transferred "+summary+" from "+source.getPlainTextName()+" to "+target.getPlainTextName()+".";
    }
    private String setFrozen(MinecraftServer server,JsonObject payload) {
        fields(payload,Set.of("player","frozen"));
        UUID id=playerId(payload,"player"); JsonElement value=payload.get("frozen");
        if (value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isBoolean()) throw new IllegalArgumentException("Invalid frozen state");
        ServerPlayer player=online(server,id); boolean freeze=value.getAsBoolean();
        if (freeze) {
            if (!frozen.containsKey(id)) {
                player.stopRiding(); frozen.put(id,new Anchor(player.level(),player.getX(),player.getY(),player.getZ()));
                enforceFrozen(player);
                if (!frozen.containsKey(id)) throw new IllegalStateException("Player movement could not be frozen. Check the server log.");
                event(player,"freeze","Movement frozen by an administrator",null);
            }
        } else thaw(player,"Unfrozen by an administrator");
        return player.getPlainTextName()+(freeze?" is frozen.":" can move again.");
    }
    private void thaw(ServerPlayer player,String reason) {
        if (frozen.remove(player.getUUID())!=null) event(player,"unfreeze",reason,null);
    }
    private void enforceFrozen(ServerPlayer player) {
        Anchor anchor=frozen.get(player.getUUID()); if (anchor==null) return;
        if (!player.isAlive() || player.isRemoved()) { thaw(player,"Player is no longer active"); return; }
        try {
            player.stopRiding();
            if (player.level()!=anchor.level() || player.distanceToSqr(anchor.x(),anchor.y(),anchor.z())>0.000001) {
                if (!player.teleportTo(anchor.level(),anchor.x(),anchor.y(),anchor.z(),Set.of(),player.getYRot(),player.getXRot(),false))
                    throw new IllegalStateException("Player did not accept the freeze position");
            }
            player.setDeltaMovement(0,0,0); player.resetFallDistance();
        } catch (RuntimeException e) { thaw(player,"Freeze stopped after a movement error"); LOG.error("Could not keep player frozen",e); }
    }
    private JsonObject executeCommand(MinecraftServer server,String command) {
        if (command.length()>4096 || command.contains("\n") || command.contains("\r") || command.indexOf('\0')>=0) throw new IllegalArgumentException("Invalid command");
        final boolean[] success={false}; final int[] result={0}; List<String> messages=new ArrayList<>();
        var sink=new net.minecraft.commands.CommandSource() {
            public void sendSystemMessage(Component message) { messages.add(message.getString()); server.sendSystemMessage(message); }
            public boolean acceptsSuccess(){return true;}
            public boolean acceptsFailure(){return true;}
            public boolean shouldInformAdmins(){return false;}
        };
        var source=server.createCommandSourceStack().withSource(sink).withCallback((ok,value)->{success[0]=ok;result[0]=value;});
        server.getCommands().performPrefixedCommand(source,command);
        JsonObject reply=new JsonObject(); reply.addProperty("ok",success[0]); reply.addProperty("result",result[0]);
        reply.addProperty("message",messages.isEmpty()?(success[0]?"Command completed":"No success returned; check console"):String.join(" | ",messages));
        event(null,"admin_command",command,null); return reply;
    }
    private void commands(MinecraftServer server) throws Exception {
        try(var files=Files.list(dir.resolve("inbox"))) {
            for(Path path:files.filter(p -> p.getFileName().toString().matches("[a-f0-9-]+\\.json")).limit(20).toList()) {
                JsonObject reply=new JsonObject(); String requestId=path.getFileName().toString(); boolean cacheAction=false;
                try {
                    if (Files.size(path)>16384) throw new IllegalArgumentException("Request is too large");
                    var request=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
                    JsonElement sentValue=request.get("time");
                    if (sentValue==null || !sentValue.isJsonPrimitive() || !sentValue.getAsJsonPrimitive().isNumber()) throw new IllegalArgumentException("Invalid request time");
                    long sent=sentValue.getAsBigDecimal().longValueExact(),now=System.currentTimeMillis();
                    if(!session.equals(text(request,"session",36,false)) || sent<now-30000 || sent>now+30000)
                        throw new IllegalArgumentException("Expired request; action was not executed");
                    if (request.has("action")) {
                        if (!requestId.matches("[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\\.json")) throw new IllegalArgumentException("Invalid request ID");
                        cacheAction=true;
                        if (completedActions.containsKey(requestId)) reply=completedActions.get(requestId).deepCopy();
                        else {
                            if (request.has("command")) throw new IllegalArgumentException("An action cannot also contain a command");
                            if (!request.has("payload") || !request.get("payload").isJsonObject()) throw new IllegalArgumentException("Invalid action payload");
                            String action=text(request,"action",32,false); JsonObject payload=request.getAsJsonObject("payload");
                            String message=switch(action) {
                                case "transfer_item"->transferItem(server,payload);
                                case "set_frozen"->setFrozen(server,payload);
                                default->throw new IllegalArgumentException("Unknown action");
                            };
                            reply.addProperty("ok",true); reply.addProperty("result",1); reply.addProperty("message",message);
                        }
                    } else reply=executeCommand(server,text(request,"command",4096,false));
                } catch(Exception e) { reply.addProperty("ok",false); reply.addProperty("message",e.getMessage()==null?"Action failed; check the server log":e.getMessage()); }
                // Retain outcomes before asynchronous reply I/O. A retry of this UUID cannot mutate twice.
                if (cacheAction) {
                    completedActions.putIfAbsent(requestId,reply.deepCopy());
                    while (completedActions.size()>1024) completedActions.remove(completedActions.keySet().iterator().next());
                }
                write(dir.resolve("replies").resolve(path.getFileName()),reply); Files.deleteIfExists(path);
            }
        }
    }
    private void write(Path path,JsonObject data) {
        String text=JSON.toJson(data);
        writer.submit(() -> {
            try { Path tmp=path.resolveSibling(path.getFileName()+".tmp"); Files.writeString(tmp,text);
                try { Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE); }
                catch(AtomicMoveNotSupportedException e) { Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING); }
            } catch(Exception e) { LOG.error("Could not write manager snapshot",e); }
        });
    }
}
