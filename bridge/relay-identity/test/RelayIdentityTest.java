package org.ev6.aare;
import android.os.SystemClock;import android.content.Context;import java.io.*;
public class RelayIdentityTest{
 static int n;static void check(boolean v){n++;if(!v)throw new AssertionError("identity "+n);}
 public static class Channel{int calls;String address;public void requestPairing(String a){calls++;address=a;}}
 static String record(String a,long end){return "EV6RELAY1|11111111111111111111111111111111|"+a+"|"+end+"|END\n";}
 public static void main(String[] args)throws Exception{
  String mac="01:11:22:33:44:55";SystemClock.now=1000;
  check(RelayIdentity.parse(record(mac,2000),1000)!=null);
  for(String a:new String[]{"00:00:00:00:00:00","02:00:00:00:00:00","FF:FF:FF:FF:FF:FF","01:11:22:33:44:55","not-a-mac"})check(RelayIdentity.parse(record(a,2000),1000)==null);
  check(RelayIdentity.parse(record(mac,1000),1000)==null);check(RelayIdentity.parse(record(mac,700000),1000)==null);check(RelayIdentity.parse("garbage",1000)==null);
  Object i=RelayIdentity.parse(record(mac,2000),1000);Channel c=new Channel();RelayIdentity.running(i);check(c.calls==0);RelayIdentity.bind(i,c);RelayIdentity.running(i);RelayIdentity.running(i);check(c.calls==1&&mac.equals(c.address));
  Channel replacement=new Channel();RelayIdentity.bind(i,replacement);RelayIdentity.running(i);check(replacement.calls==0);
  i=RelayIdentity.parse(record(mac,2000),1000);RelayIdentity.bind(i,replacement);SystemClock.now=2000;RelayIdentity.running(i);check(replacement.calls==0);
  File dir=new File(args[0]);dir.mkdir();File f=new File(dir,RelayIdentity.FILE);FileOutputStream out=new FileOutputStream(f);out.write(record(mac,3000).getBytes("US-ASCII"));out.close();Context context=new Context(dir);
  check(RelayIdentity.capture(context,false,"tcp")==null&&f.exists());check(RelayIdentity.capture(context,true,"usb")==null&&f.exists());check(RelayIdentity.capture(context,true,"tcp")!=null&&!f.exists());check(RelayIdentity.capture(context,true,"tcp")==null);
  // Android may expose its private directory through /data/data versus /data/user/0.
  out=new FileOutputStream(f);out.write(record(mac,3000).getBytes("US-ASCII"));out.close();
  File alias=new File(dir.getParentFile(),"alias");java.nio.file.Files.createSymbolicLink(alias.toPath(),dir.toPath());
  check(RelayIdentity.capture(new Context(alias),true,"tcp")!=null&&!f.exists());
  File external=new File(dir.getParentFile(),"outside");out=new FileOutputStream(external);out.write(record(mac,3000).getBytes("US-ASCII"));out.close();
  java.nio.file.Files.createSymbolicLink(f.toPath(),external.toPath());
  check(RelayIdentity.capture(context,true,"tcp")==null&&external.exists());
  System.out.println("RELAY_IDENTITY_CHECKS="+n);
 }
}
