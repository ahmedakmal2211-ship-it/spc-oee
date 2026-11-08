"""Published constants used by the SPC and OEE calculations.

Control-chart constants are the standard tabulated factors for subgroup size n,
as given in Montgomery, "Introduction to Statistical Quality Control",
Appendix VI (the same values appear in most SPC textbooks).
"""

# Subgroup size n -> factor, for n = 2..10.
A2 = {2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577, 6: 0.483,
      7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308}
D3 = {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0,
      7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223}
D4 = {2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114, 6: 2.004,
      7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777}
D2 = {2: 1.128, 3: 1.693, 4: 2.059, 5: 2.326, 6: 2.534,
      7: 2.704, 8: 2.847, 9: 2.970, 10: 3.078}

MIN_SUBGROUP = 2
MAX_SUBGROUP = 10  # largest n handled by the Xbar-R chart

# Individuals and Moving Range chart (moving range of span 2).
IMR_D2 = 1.128      # d2 for n = 2
IMR_E2 = 2.660      # 3 / d2, multiplies MRbar for the I-chart limits
IMR_D3 = 0.0
IMR_D4 = 3.267

# World-class OEE reference. Informational only: it is a common industry
# convention popularised via Seiichi Nakajima's TPM work, not a standard.
WORLD_CLASS_OEE = 0.85
WORLD_CLASS_OEE_NOTE = (
    "85% 'world-class' OEE is a common industry convention "
    "(after Nakajima, TPM), not a standard; use it as a rough reference only."
)
