using System;
using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// Fires <see cref="Pinched"/> once per index-finger pinch on either hand.
    /// A controller trigger counts too, which helps when testing.
    /// </summary>
    public class PinchInput : MonoBehaviour
    {
        public OVRHand leftHand;
        public OVRHand rightHand;

        [Tooltip("Ignore new pinches for this long after one fires.")]
        public float cooldown = 0.5f;

        public event Action Pinched;

        bool _wasPinching;
        float _readyAt;

        void Update()
        {
            var pinching = IsPinching(leftHand) || IsPinching(rightHand)
                || OVRInput.Get(OVRInput.Button.PrimaryIndexTrigger, OVRInput.Controller.Touch);
            if (pinching && !_wasPinching && Time.time >= _readyAt)
            {
                _readyAt = Time.time + cooldown;
                Pinched?.Invoke();
            }
            _wasPinching = pinching;
        }

        static bool IsPinching(OVRHand hand) =>
            hand != null && hand.IsTracked && hand.GetFingerIsPinching(OVRHand.HandFinger.Index);
    }
}
