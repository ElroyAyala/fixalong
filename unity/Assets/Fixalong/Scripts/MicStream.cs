using System.Collections.Generic;
using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// Streams the microphone to the server as 24 kHz 16-bit mono PCM in 100 ms
    /// chunks. While Felix talks it sends silence instead: he never hears
    /// himself, and the transcription stream keeps its real-time pace (Meta
    /// closes it if audio falls behind).
    /// </summary>
    public class MicStream : MonoBehaviour
    {
        public FelixLink link;

        [Tooltip("Felix's voice. The mic is muted while it plays.")]
        public AudioSource felixVoice;

        [Tooltip("Stay muted this long after Felix stops, so his last word's echo dies away.")]
        public float muteTail = 0.3f;

        const int OutputRate = 24000;
        const int ChunkSamples = OutputRate / 10;

        string _device;
        AudioClip _clip;
        int _readPosition;
        float _step;   // mic samples per output sample
        double _phase; // position in _input of the next output sample
        float _mutedUntil;
        readonly List<float> _input = new();
        readonly List<short> _output = new();

        /// <summary>Start listening. Call once the microphone permission is granted.</summary>
        public void StartMic()
        {
            if (_clip != null) return;
            if (Microphone.devices.Length == 0)
            {
                Debug.LogWarning("[fixalong] no microphone found");
                return;
            }
            _device = Microphone.devices[0];
            Microphone.GetDeviceCaps(_device, out var minRate, out var maxRate);
            var rate = minRate == 0 && maxRate == 0 ? OutputRate : Mathf.Clamp(OutputRate, minRate, maxRate);
            _clip = Microphone.Start(_device, true, 1, rate);
            _step = _clip.frequency / (float)OutputRate;
            Debug.Log($"[fixalong] microphone '{_device}' running at {_clip.frequency} Hz");
        }

        void OnDestroy()
        {
            if (_clip != null) Microphone.End(_device);
        }

        void Update()
        {
            if (_clip == null) return;
            var position = Microphone.GetPosition(_device);
            var count = (position - _readPosition + _clip.samples) % _clip.samples;
            if (count == 0) return;
            ReadClip(_readPosition, count);
            _readPosition = position;

            if (felixVoice != null && felixVoice.isPlaying) _mutedUntil = Time.time + muteTail;
            Resample(muted: Time.time < _mutedUntil);

            while (_output.Count >= ChunkSamples)
            {
                var bytes = new byte[ChunkSamples * 2];
                for (var i = 0; i < ChunkSamples; i++)
                {
                    var sample = _output[i];
                    bytes[2 * i] = (byte)sample;
                    bytes[2 * i + 1] = (byte)(sample >> 8);
                }
                _output.RemoveRange(0, ChunkSamples);
                if (link.IsConnected) link.SendBinary(bytes);
            }
        }

        // The mic writes into a looping clip, so new samples can wrap past its end.
        void ReadClip(int start, int count)
        {
            var first = Mathf.Min(count, _clip.samples - start);
            AppendSamples(start, first);
            if (count > first) AppendSamples(0, count - first);
        }

        void AppendSamples(int offset, int count)
        {
            var buffer = new float[count];
            _clip.GetData(buffer, offset);
            _input.AddRange(buffer);
        }

        // Linear resampling from the mic's rate to 24 kHz. Muted stretches become
        // silence but keep their length, so the stream stays at real-time pace.
        void Resample(bool muted)
        {
            while (_phase + 1 < _input.Count)
            {
                var i = (int)_phase;
                var sample = muted ? 0f : Mathf.Lerp(_input[i], _input[i + 1], (float)(_phase - i));
                _output.Add((short)(Mathf.Clamp(sample, -1f, 1f) * short.MaxValue));
                _phase += _step;
            }
            var used = (int)_phase;
            _input.RemoveRange(0, used);
            _phase -= used;
        }
    }
}
