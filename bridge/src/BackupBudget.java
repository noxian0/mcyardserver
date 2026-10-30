package dev.mcyard.bridge;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.level.storage.LevelResource;

public final class BackupBudget {
    public static final long LIMIT=50_000_000_000L, HEADROOM=64L*1024*1024;
    private static final ThreadLocal<Long> REMAINING=new ThreadLocal<>();
    private static final ThreadLocal<Boolean> FAILED=ThreadLocal.withInitial(()->false);
    private static final Path ROOT=Path.of("backups").toAbsolutePath().normalize();
    public static long size(Path path) throws IOException {
        if(!Files.exists(path))return 0;
        if(Files.isRegularFile(path))return Files.size(path);
        try(var paths=Files.walk(path)) {
            long total=0;
            for(Path p:paths.filter(p->Files.isRegularFile(p,LinkOption.NOFOLLOW_LINKS)).toList())total=Math.addExact(total,Files.size(p));
            return total;
        }
    }
    public static void begin(MinecraftServer server) throws IOException {
        FAILED.set(false);REMAINING.remove();
        Files.createDirectories(ROOT);
        long raw=size(server.getWorldPath(LevelResource.ROOT));
        long required=Math.addExact(Math.multiplyExact(raw,2),raw/20+HEADROOM);
        // Tests may lower the limit; no property can raise the production ceiling.
        long ceiling=Math.min(LIMIT,Long.getLong("mcyard.backup.limitBytes",LIMIT))-HEADROOM;
        if(required>ceiling)throw new IOException("Backup cannot fit under the 50 GB total limit, including temporary copy. Existing backups preserved.");
        List<Path> groups=new ArrayList<>();
        try(var files=Files.walk(ROOT)) {
            for(Path p:files.filter(p->Files.isRegularFile(p,LinkOption.NOFOLLOW_LINKS)&&p.toString().endsWith(".zip")).toList()) {
                if(p.getFileName().toString().equals("full.zip") && p.startsWith(ROOT.resolve("world")))groups.add(p.getParent());
                else if(p.getParent().equals(ROOT)||p.getParent().equals(ROOT.resolve("full-server")))groups.add(p);
            }
        }
        groups.sort(Comparator.comparingLong(p->{try{return Files.getLastModifiedTime(Files.isDirectory(p)?p.resolve("full.zip"):p).toMillis();}catch(IOException e){return Long.MAX_VALUE;}}));
        long used=size(ROOT),reclaimable=0;
        for(int i=0;i<groups.size()-1;i++)reclaimable+=size(groups.get(i));
        if(used-reclaimable+required>ceiling)throw new IOException("50 GB backup limit: cannot make space while preserving the newest completed backup.");
        for(int i=0;i<groups.size()-1 && used+required>ceiling;i++) {
            Path old=groups.get(i);deleteSafe(old);used=size(ROOT);
            System.out.println("[MCyard Server] Removed oldest backup for 50 GB limit: "+old);
        }
        REMAINING.set(ceiling-used);
    }
    private static void deleteSafe(Path path) throws IOException {
        Path root=ROOT.toRealPath();
        try(var stream=Files.walk(path)) {
            var files=stream.toList();
            for(Path p:files)if(Files.isSymbolicLink(p)||!p.toRealPath().startsWith(root)||p.toRealPath().equals(root))throw new IOException("Unsafe backup retention target: "+p);
            for(Path p:files.stream().sorted(Comparator.reverseOrder()).toList())Files.delete(p);
        }
    }
    public static OutputStream output(Path path,OpenOption... options) throws IOException {
        if(REMAINING.get()==null)throw new IOException("Backup space reservation missing");
        return new FilterOutputStream(Files.newOutputStream(path,options)) {
            private void claim(int bytes) throws IOException {
                long left=REMAINING.get();
                if(bytes>left){FAILED.set(true);throw new IOException("Stopped backup before exceeding the 50 GB total limit");}
                REMAINING.set(left-bytes);
            }
            public void write(int value)throws IOException{claim(1);out.write(value);}
            public void write(byte[] bytes,int offset,int length)throws IOException{claim(length);out.write(bytes,offset,length);}
        };
    }
    public static Path copy(Path from,Path to)throws IOException {
        try(var input=Files.newInputStream(from);var output=output(to,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){input.transferTo(output);}
        Files.setLastModifiedTime(to,Files.getLastModifiedTime(from));
        return to;
    }
    public static void finish(Path archive)throws IOException {
        if(FAILED.get()) {
            Files.deleteIfExists(archive);
            throw new IOException("Backup exceeded its 50 GB space reservation; incomplete archive removed");
        }
        REMAINING.remove();
    }
}
