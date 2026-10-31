using UnityEngine;

namespace Fixalong
{
    /// <summary>
    /// A comfortable spot beside your line of sight that follows where you
    /// look, down and up as well as left and right, so Felix and his checklist
    /// stay in view when you look down at your work. Looking level, the spot
    /// sits a little below eye height; looking down, it comes closer and rides
    /// toward the top of your view, clear of your hands.
    /// </summary>
    public static class ViewSpot
    {
        // Degrees: looking further down than this doesn't move the spot further. Looking
        // into a toilet tank is about 70-85 degrees, so the spot follows nearly all the way.
        const float MaxDown = 80f;
        const float MaxUp = 20f;
        const float FullyDown = 50f; // the pitch at which the "looking down" spot fully applies

        /// <param name="level">Where it sits when you look level, in meters: x right of your
        /// line of sight (negative is left), y toward the top of your view, z ahead.</param>
        /// <param name="down">Where it sits when you look down at your work.</param>
        public static Vector3 Home(Transform head, Vector3 level, Vector3 down)
        {
            var forward = head.forward;
            var flat = Vector3.ProjectOnPlane(forward, Vector3.up);
            if (flat.sqrMagnitude < 0.001f) flat = Vector3.ProjectOnPlane(head.up, Vector3.up);
            flat.Normalize();
            var pitchDown = Mathf.Asin(Mathf.Clamp(-forward.y, -1f, 1f)) * Mathf.Rad2Deg;
            pitchDown = Mathf.Clamp(pitchDown, -MaxUp, MaxDown);
            var t = Mathf.Clamp01(pitchDown / FullyDown);
            // No roll: tilting your head doesn't swing the spot around.
            var view = Quaternion.LookRotation(flat, Vector3.up) * Quaternion.Euler(pitchDown, 0f, 0f);
            return head.position + view * Vector3.Lerp(level, down, t);
        }
    }

    /// <summary>
    /// Keeps something near its view spot without chasing every small head
    /// movement: it holds still until it's drifted too far out of place, then
    /// glides back. Drift is measured as an angle from your eyes, so it never
    /// leaves your view before it starts back, near or far.
    /// </summary>
    public class ViewFollow
    {
        readonly float _driftDegrees;
        readonly float _driftMeters; // for walking toward or away from it
        readonly float _sharpness;
        bool _placed;
        bool _returning;

        public ViewFollow(float driftDegrees, float driftMeters, float sharpness)
        {
            _driftDegrees = driftDegrees;
            _driftMeters = driftMeters;
            _sharpness = sharpness;
        }

        /// <summary>The next time it moves, it appears at its spot instead of gliding.</summary>
        public void Reset() => _placed = false;

        public Vector3 Step(Vector3 current, Vector3 home, Vector3 eye)
        {
            if (!_placed)
            {
                _placed = true;
                return home;
            }
            var offset = Vector3.Distance(current, home);
            if (Vector3.Angle(current - eye, home - eye) > _driftDegrees || offset > _driftMeters)
                _returning = true;
            if (!_returning) return current;
            if (offset < 0.02f) _returning = false;
            return Vector3.Lerp(current, home, 1f - Mathf.Exp(-_sharpness * Time.deltaTime));
        }
    }
}
