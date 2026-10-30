package dev.mcyard.bridge.mixin;
import dev.mcyard.bridge.BackupBudget;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import org.spongepowered.asm.mixin.injection.callback.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.storage.LevelStorageSource;
import de.melanx.simplebackups.compression.CompressionBase;
import java.nio.file.Path;
import java.io.IOException;

@Mixin(value=CompressionBase.class,remap=false)
public abstract class BackupCompressionMixin {
    @Inject(method="makeBackup(Lnet/minecraft/server/MinecraftServer;Lnet/minecraft/world/level/storage/LevelStorageSource$LevelStorageAccess;Ljava/nio/file/Path;Ljava/nio/file/Path;ZLde/melanx/simplebackups/compression/CompressionBase$BackupFormat;J)Lde/melanx/simplebackups/BackupResult;",at=@At("HEAD"))
    private static void budget(MinecraftServer server,LevelStorageSource.LevelStorageAccess storage,Path dir,Path file,boolean full,CompressionBase.BackupFormat format,long saved,CallbackInfoReturnable<?> ci)throws IOException {
        if(format!=CompressionBase.BackupFormat.ZIP)throw new IOException("50 GB safety guard requires ZIP backups");
        BackupBudget.begin(server);
    }
    @Inject(method="makeBackup(Lnet/minecraft/server/MinecraftServer;Lnet/minecraft/world/level/storage/LevelStorageSource$LevelStorageAccess;Ljava/nio/file/Path;Ljava/nio/file/Path;ZLde/melanx/simplebackups/compression/CompressionBase$BackupFormat;J)Lde/melanx/simplebackups/BackupResult;",at=@At("RETURN"))
    private static void finish(MinecraftServer server,LevelStorageSource.LevelStorageAccess storage,Path dir,Path file,boolean full,CompressionBase.BackupFormat format,long saved,CallbackInfoReturnable<?> ci)throws IOException {
        BackupBudget.finish(file);
    }
}
