# Field test logs

On November 1, four first-timers each tried to fix a real toilet with Felix, alone with the headset and one line to say. I staged an installation mistake beforehand and didn't tell them what it was. These are the structured job logs the server wrote for each run, unedited. The photos and audio they point to stay private, because they were taken in a family home.

| Log | First-timer | Staged fault | How it ended |
|---|---|---|---|
| [run1.json](run1.json) | My son, 14 | Flapper ear off its peg | Stopped. An unsure answer ruled out the flapper, and Felix went for a fill valve swap. Water still seemed to come in with the shutoff valve closed, so he stopped the job and said to call a plumber. |
| [run2.json](run2.json) | My 27-year-old | Flapper ear off its peg | Fixed |
| [run3.json](run3.json) | My daughter, 13 | Chain too tight | Fixed. She clipped a flapper ear and rehooked the chain with slack, and the closeout lists both, but its diagnosis and tip credit the ear. The chain was the staged fault. Felix's closeout now credits every change when the proof can't tell which one did it. |
| [run4.json](run4.json) | My wife, not a VR fan | Chain too tight | Fixed, from greeting to goodbye in under three minutes |

What each log holds, with times in seconds from the start of the session:

- `problem`, `experience`: Felix's one-sentence summary of the problem, and how much the person has done this before.
- `causes_over_time`: the possible causes each time Felix updated them, with priors and the evidence for and against each.
- `probes`: each test, declared before the person acted: the instruction, what to observe, and which causes each outcome supports or rules out. Then the result.
- `steps`: the repair steps, each with its pass condition and every attempt.
- `verifications`: the separate verifier's verdict on each step or safety check, with what it saw and its correction for a "not yet."
- `cautions`: each hazard sign: when it was found, shown, seen and acknowledged.
- `closeout` or `stopped`: the cause, the evidence and the proof, or why the job stopped.
