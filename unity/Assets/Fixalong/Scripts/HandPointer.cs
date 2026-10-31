using System;
using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// Your hands as pointers, as at the Quest's own menus: where a hand's
    /// pointer meets a flat panel facing you, and when a pinch starts. The
    /// pointer is the Quest's own: it isn't valid while your palm faces you for
    /// the system menu.
    /// </summary>
    public static class HandPointer
    {
        /// <summary>Where the hand's pointer meets the plane of surface (its forward points
        /// away from you), and how far along the pointer.</summary>
        public static bool Hit(OVRHand hand, Transform surface, float maxReach, out Vector3 hit,
            out float distance)
        {
            hit = default;
            distance = 0f;
            if (hand == null || !hand.IsTracked || !hand.IsPointerPoseValid || hand.IsSystemGestureInProgress)
                return false;
            var pointer = hand.PointerPose;
            var facing = Vector3.Dot(pointer.forward, surface.forward);
            if (facing < 0.2f) return false; // pointing away, or along the panel
            distance = Vector3.Dot(surface.position - pointer.position, surface.forward) / facing;
            if (distance <= 0f || distance > maxReach) return false;
            hit = pointer.position + pointer.forward * distance;
            return true;
        }

        /// <summary>Whether a point on a panel is inside one of its rectangles.</summary>
        public static bool Contains(RectTransform rect, Vector3 world) =>
            rect.rect.Contains(rect.InverseTransformPoint(world));
    }

    /// <summary>Each hand's index pinch, frame to frame.</summary>
    public class Pinches
    {
        bool[] _pinching = Array.Empty<bool>();

        /// <summary>Which hands just started a pinch this frame. Call once a frame.</summary>
        public bool[] Read(OVRHand[] hands)
        {
            if (_pinching.Length != hands.Length) _pinching = new bool[hands.Length];
            var started = new bool[hands.Length];
            for (var i = 0; i < hands.Length; i++)
            {
                var hand = hands[i];
                var pinching = hand != null && hand.IsTracked && hand.GetFingerIsPinching(OVRHand.HandFinger.Index);
                started[i] = pinching && !_pinching[i];
                _pinching[i] = pinching;
            }
            return started;
        }

        /// <summary>Whether this hand is still pinching.</summary>
        public bool Holding(int hand) => hand < _pinching.Length && _pinching[hand];
    }
}
