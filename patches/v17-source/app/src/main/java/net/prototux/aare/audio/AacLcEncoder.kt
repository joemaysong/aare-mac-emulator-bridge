package net.prototux.aare.audio

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaCodecList
import android.media.MediaFormat

/** One encoder per playback lifetime. Raw AAC-LC frames plus AudioSpecificConfig. */
internal class AacLcEncoder(private val rate: Int, private val channels: Int,
    private val config: (ByteArray) -> Unit, private val frame: (ByteArray, Long) -> Unit) : AutoCloseable {
    private val codec = MediaCodec.createEncoderByType(MediaFormat.MIMETYPE_AUDIO_AAC)
    private val info = MediaCodec.BufferInfo()
    init {
        try { codec.configure(format(rate, channels), null, null, MediaCodec.CONFIGURE_FLAG_ENCODE); codec.start() }
        catch (failure: Exception) { codec.release(); throw failure }
    }
    fun encode(pcm: ByteArray, offset: Int, length: Int, timestampUs: Long) {
        require(length % (channels * 2) == 0)
        var used = 0
        drain()
        while (used < length) {
            val index = codec.dequeueInputBuffer(10_000)
            check(index >= 0) { "AAC encoder input stalled" }
            val input = checkNotNull(codec.getInputBuffer(index)); input.clear()
            val bytes = minOf(input.remaining(), length - used) / (channels * 2) * (channels * 2)
            check(bytes > 0)
            input.put(pcm, offset + used, bytes)
            codec.queueInputBuffer(index, 0, bytes, timestampUs + used.toLong() / (channels * 2) * 1_000_000L / rate, 0)
            used += bytes
            drain()
        }
    }
    private fun drain() {
        while (true) {
            val index = codec.dequeueOutputBuffer(info, 0)
            if (index == MediaCodec.INFO_TRY_AGAIN_LATER) return
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                codec.outputFormat.getByteBuffer("csd-0")?.duplicate()?.let { b ->
                    config(ByteArray(b.remaining()).also { b.get(it) })
                }
            } else if (index >= 0) {
                try {
                    if (info.size > 0 && info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG == 0) {
                        val b = checkNotNull(codec.getOutputBuffer(index)).duplicate()
                        b.position(info.offset); b.limit(info.offset + info.size)
                        frame(ByteArray(info.size).also { b.get(it) }, info.presentationTimeUs)
                    }
                } finally { codec.releaseOutputBuffer(index, false) }
            }
        }
    }
    override fun close() { try { codec.stop() } finally { codec.release() } }
    companion object {
        private fun format(rate: Int, channels: Int) = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_AAC, rate, channels).apply {
            setInteger(MediaFormat.KEY_AAC_PROFILE, MediaCodecInfo.CodecProfileLevel.AACObjectLC)
            setInteger(MediaFormat.KEY_BIT_RATE, if (channels == 1) 96_000 else 192_000)
            setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 16_384)
        }
        fun supported(rate: Int, channels: Int): Boolean = rate > 0 && channels in 1..2 &&
            runCatching { MediaCodecList(MediaCodecList.REGULAR_CODECS).findEncoderForFormat(format(rate, channels)) != null }.getOrDefault(false)
    }
}
