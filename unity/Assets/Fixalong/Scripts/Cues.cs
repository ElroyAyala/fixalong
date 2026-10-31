using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// Short sound cues, each heard from where it happens, so you can tell
    /// where something just showed up without looking for it: a pop for a new
    /// part label, a woosh when the checklist appears or moves to its next
    /// list, a click when a mark on it changes, a chime for the two big
    /// moments (the cause found and the job fixed), a blip from Felix when he
    /// hears his name, and a caution tone for a hazard sign. Kept quiet next to
    /// Felix's voice.
    /// </summary>
    public class Cues : MonoBehaviour
    {
        public AudioClip pop;
        public AudioClip click;
        public AudioClip woosh;
        public AudioClip chime;
        public AudioClip listen;
        public AudioClip caution;
        [Range(0f, 1f)] public float volume = 0.45f;

        const int Voices = 4; // a few at once, like labels popping in one after another
        AudioSource[] _voices;
        int _next;

        void Awake()
        {
            _voices = new AudioSource[Voices];
            for (var i = 0; i < Voices; i++)
            {
                var voice = new GameObject("Cue").AddComponent<AudioSource>();
                voice.transform.SetParent(transform, false);
                voice.playOnAwake = false;
                voice.spatialBlend = 1f; // heard from where it happens
                voice.minDistance = 1f; // full volume within arm's reach
                _voices[i] = voice;
            }
        }

        public void Play(AudioClip clip, Vector3 at)
        {
            if (clip == null) return;
            var voice = _voices[_next];
            _next = (_next + 1) % Voices;
            voice.transform.position = at;
            voice.clip = clip;
            voice.volume = volume;
            voice.Play();
        }
    }
}
