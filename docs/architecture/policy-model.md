# Policy model

Policies match a pattern and minimum threshold, then produce an intervention. Rules
are sorted deterministically by priority, threshold, and declaration order. Terminal
interventions outrank non-terminal ones; ties preserve explicit priority. Threshold
crossing and cooldown are evaluated before emission so a once-only nudge is not spammed.

