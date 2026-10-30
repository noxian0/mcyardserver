package dev.mcyard.bridge.mixin;
import dev.mcyard.bridge.BackupBudget;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.*;
import java.nio.file.*;
import java.io.IOException;

@Mixin(targets="de.melanx.simplebackups.compression.CompressionBase$PreCopyFileVisitor",remap=false)
public abstract class BackupCopyMixin {
    @Redirect(method="visitFile_",at=@At(value="INVOKE",target="Ljava/nio/file/Files;copy(Ljava/nio/file/Path;Ljava/nio/file/Path;[Ljava/nio/file/CopyOption;)Ljava/nio/file/Path;"))
    private Path copy(Path source,Path dest,CopyOption[] options)throws IOException {
        return BackupBudget.copy(source,dest);
    }
}
