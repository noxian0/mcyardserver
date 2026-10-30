package dev.mcyard.bridge.mixin;
import dev.mcyard.bridge.BackupBudget;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import de.melanx.simplebackups.compression.ZipCompression;
import java.nio.file.*;
import java.io.*;

@Mixin(value=ZipCompression.class,remap=false)
public abstract class BackupZipMixin {
    @Redirect(method="makeBackup",at=@At(value="INVOKE",target="Ljava/nio/file/Files;newOutputStream(Ljava/nio/file/Path;[Ljava/nio/file/OpenOption;)Ljava/io/OutputStream;"))
    private OutputStream limited(Path path,OpenOption[] options)throws IOException{return BackupBudget.output(path,options);}
}
