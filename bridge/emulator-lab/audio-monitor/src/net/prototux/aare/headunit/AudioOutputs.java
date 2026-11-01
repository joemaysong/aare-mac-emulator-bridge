package net.prototux.aare.headunit;
// Local diagnostic audio sink for the unmodified GPL-3.0 AARE headunit distribution.
// Same PCM playback interface as upstream, plus bounded PCM evidence for this emulator-only lab.
import aap_protobuf.service.media.shared.message.AudioConfigurationOuterClass.AudioConfiguration;
import aap_protobuf.service.media.sink.message.AudioStreamTypeOuterClass.AudioStreamType;
import javax.sound.sampled.*;import java.util.concurrent.*;import java.io.*;import java.util.*;
public final class AudioOutputs {
 final Map<AudioStreamType,Player> players=new ConcurrentHashMap<>();
 public void start(AudioStreamType s,AudioConfiguration c){stop(s);try{players.put(s,new Player(s,c));}catch(Exception e){System.err.println("LAB_AUDIO_ERROR "+e);}}
 public void write(AudioStreamType s,byte[] b,int o,int n){Player p=players.get(s);if(p!=null)p.add(Arrays.copyOfRange(b,o,o+n));}
 public void stop(AudioStreamType s){Player p=players.remove(s);if(p!=null)p.close();}
 public void close(){for(AudioStreamType s:new ArrayList<>(players.keySet()))stop(s);}
 static final class Player {final AudioStreamType stream;final SourceDataLine line;final LinkedBlockingDeque<byte[]> queue=new LinkedBlockingDeque<>();final FileOutputStream capture;final int rate,channels,bits;volatile boolean running=true;long bytes,played,energy,samples;int peak;long last;final Thread thread;
 Player(AudioStreamType s,AudioConfiguration c)throws Exception{stream=s;rate=c.getSamplingRate();channels=c.getNumberOfChannels();bits=c.getNumberOfBits();AudioFormat f=new AudioFormat(rate,bits,channels,true,false);line=AudioSystem.getSourceDataLine(f);line.open(f,rate*channels*(bits/8)*300/1000);line.start();File dir=new File(System.getProperty("aare.lab.evidence"));dir.mkdirs();capture=Boolean.getBoolean("aare.lab.capture")?new FileOutputStream(new File(dir,"audio-"+s.name()+"-"+System.currentTimeMillis()+".pcm")):null;System.out.println("LAB_AUDIO_START stream="+s+" rate="+rate+" channels="+channels+" bits="+bits+" output="+line.getLineInfo());thread=new Thread(()->{try{while(running){byte[] b=queue.poll(100,TimeUnit.MILLISECONDS);if(b!=null){int n=line.write(b,0,b.length);played+=n;}}}catch(Exception e){System.err.println("LAB_AUDIO_PLAY_ERROR "+e);}finally{line.stop();line.close();}},"lab-audio-"+s);thread.setDaemon(true);thread.start();}
 synchronized void add(byte[] b){bytes+=b.length;if(bits==16)for(int i=0;i+1<b.length;i+=2){int x=(short)((b[i]&255)|(b[i+1]<<8));peak=Math.max(peak,Math.abs(x));energy+=(long)x*x;samples++;}try{if(capture!=null && capture.getChannel().position()+b.length<=4000000)capture.write(b);}catch(Exception e){System.err.println("LAB_AUDIO_CAPTURE_ERROR "+e);}if(queue.size()>60)queue.poll();queue.offer(b);long now=System.currentTimeMillis();if(now-last>1000){last=now;stats();}}
 synchronized void stats(){System.out.println("LAB_AUDIO_STATS stream="+stream+" received_bytes="+bytes+" played_bytes="+played+" peak="+peak+" rms="+(samples==0?0:Math.sqrt((double)energy/samples)));System.out.flush();try{java.nio.file.Files.writeString(new File(System.getProperty("aare.lab.evidence"),"audio-stats-"+stream+".json").toPath(),"{\"rate\":"+rate+",\"channels\":"+channels+",\"bits\":"+bits+",\"received_bytes\":"+bytes+",\"played_bytes\":"+played+",\"peak\":"+peak+",\"rms\":"+(samples==0?0:Math.sqrt((double)energy/samples))+"}");}catch(Exception ignored){}}
 synchronized void close(){running=false;thread.interrupt();stats();try{if(capture!=null)capture.close();}catch(Exception ignored){}}
 }
}
