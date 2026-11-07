package android.content;import java.io.File;public class Context{private final File f;public Context(File f){this.f=f;}public File getFilesDir(){return f;}}
