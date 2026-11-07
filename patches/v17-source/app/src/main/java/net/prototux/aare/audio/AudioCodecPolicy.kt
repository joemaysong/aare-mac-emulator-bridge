package net.prototux.aare.audio

import aap_protobuf.service.ServiceOuterClass.Service
import aap_protobuf.service.media.shared.message.MediaCodecTypeOuterClass.MediaCodecType

/** Never substitute a codec the receiver did not advertise. */
object AudioCodecPolicy {
    @JvmStatic fun supports(service: Service): Boolean {
        val sink = service.mediaSinkService
        return when (sink.availableType) {
            MediaCodecType.MEDIA_CODEC_AUDIO_PCM -> true
            MediaCodecType.MEDIA_CODEC_AUDIO_AAC_LC -> sink.audioConfigsCount > 0 && sink.audioConfigsList.all {
                it.numberOfBits == 16 && AacLcEncoder.supported(it.samplingRate, it.numberOfChannels)
            }
            else -> false
        }
    }
}
