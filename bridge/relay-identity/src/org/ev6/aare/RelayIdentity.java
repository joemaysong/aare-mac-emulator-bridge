package org.ev6.aare;
import android.content.Context;
import android.os.SystemClock;
import android.util.Log;
import java.io.*;
/** Test relay only: one-shot, expiring identity from the actual Mac Bluetooth adapter. */
public final class RelayIdentity {
 public static final String FILE="ev6-relay-identity";
 private final String address;private final long expires;private Object channel;private boolean sent;
 private RelayIdentity(String address,long expires){this.address=address;this.expires=expires;}
 static RelayIdentity parse(String line,long now){
  String[] p=line.split("\\|",-1);
  if(p.length!=5||!p[0].equals("EV6RELAY1")||!p[1].matches("[0-9a-f]{32}")||!p[2].matches("(?:[0-9A-F]{2}:){5}[0-9A-F]{2}")||!p[3].matches("[0-9]{1,16}")||!p[4].equals("END\n"))return null;
  int first=Integer.parseInt(p[2].substring(0,2),16);long end=Long.parseLong(p[3]);
  if((first&1)!=0||p[2].equals("00:00:00:00:00:00")||p[2].equals("02:00:00:00:00:00")||end<=now||end-now>650000)return null;
  return new RelayIdentity(p[2],end);
 }
 public static Object capture(Context context,boolean wireless,String peer){
  File f;
  try{f=new File(context.getFilesDir().getCanonicalFile(),FILE);}catch(IOException unavailable){return null;}
  if(!wireless||!"tcp".equals(peer)){if(f.exists())Log.w("AareRelayIdentity","identity rejected: transport role");return null;}
  try{
   if(!f.exists())return null;
   if(!f.getCanonicalFile().equals(f.getAbsoluteFile())||!f.isFile()||f.length()>160){Log.w("AareRelayIdentity","identity rejected: private file path or size");return null;}
   byte[] b=new byte[160];int n;
   FileInputStream in=new FileInputStream(f);try{n=in.read(b);if(n<=0||in.read()!=-1)return null;}finally{in.close();}
   RelayIdentity identity=parse(new String(b,0,n,"US-ASCII"),SystemClock.elapsedRealtime());
   if(identity==null){Log.w("AareRelayIdentity","identity rejected: schema or expiry");return null;}
   if(!f.delete()){Log.w("AareRelayIdentity","identity rejected: consume failed");return null;}
   Log.i("AareRelayIdentity","identity captured for relay session");return identity;
  }catch(Exception unavailable){Log.w("AareRelayIdentity","identity rejected: private file read failed");return null;}
 }
 public static void bind(Object captured,Object channel){if(captured instanceof RelayIdentity){RelayIdentity i=(RelayIdentity)captured;synchronized(i){if(!i.sent&&i.channel==null)i.channel=channel;}}}
 public static void running(Object captured){
  if(!(captured instanceof RelayIdentity))return;RelayIdentity i=(RelayIdentity)captured;Object target;
  synchronized(i){if(i.sent||i.channel==null||SystemClock.elapsedRealtime()>=i.expires)return;i.sent=true;target=i.channel;}
  try{target.getClass().getMethod("requestPairing",String.class).invoke(target,i.address);Log.i("AareRelayIdentity","pairing identity request sent");}
  catch(Exception failed){Log.w("AareRelayIdentity","pairing identity request failed");}
 }
 public static void response(boolean paired,boolean ok){Log.i("AareRelayIdentity","pairing response: paired="+paired+", ok="+ok);}
}
