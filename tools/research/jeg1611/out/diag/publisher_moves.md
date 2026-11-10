# JEG-1611 diagnostic: publishers' own Standard-to-Full moves (dev weeks 5-7)

Sets: common = RB/WR/TE in the l_gate scored set with all four columns > 0. Intervals: 95% percentile bootstrap, 2000 resamples over players (player-clustered when pooled), seed 1611. ROS actuals: 2026 weeks w..9.

## 1. Spread of the de-meaned move m = log(F/S) (common set, pooled weeks)

| Pub | Pos | n | SD m (de-meaned) | SD full-strength hist move | share = median (exact) | share within 1% |
| --- | --- | --- | --- | --- | --- | --- |
| cbs | RB | 104 | 0.054 | 0.0578 | 0.0288 | 0.2019 |
| cbs | WR | 105 | 0.0671 | 0.0462 | 0.0095 | 0.0952 |
| cbs | TE | 35 | 0.0825 | 0.0599 | 0.1143 | 0.1143 |
| cbs | ALL | 244 | 0.0642 | 0.0532 | 0.0328 | 0.1434 |
| usatoday | RB | 104 | 0.0713 | 0.0578 | 0.0 | 0.2115 |
| usatoday | WR | 105 | 0.0466 | 0.0462 | 0.0286 | 0.2762 |
| usatoday | TE | 35 | 0.0395 | 0.0599 | 0.0286 | 0.2571 |
| usatoday | ALL | 244 | 0.0575 | 0.0532 | 0.0164 | 0.2459 |

## 2. CBS vs USA Today (common set)

| Week | Pos | n | move Spearman | move Pearson | slope CBS on USAT | Full level Sp. | Std level Sp. |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | RB | 34 | 0.702 [0.436, 0.863] | 0.617 [0.421, 0.790] | 0.552 [0.410, 0.799] | 0.964 [0.897, 0.986] | 0.959 [0.888, 0.986] |
| 5 | WR | 36 | -0.143 [-0.498, 0.215] | 0.086 [-0.451, 0.457] | 0.112 [-0.798, 0.557] | 0.929 [0.838, 0.965] | 0.930 [0.844, 0.969] |
| 5 | TE | 13 | 0.013 [-0.693, 0.684] | 0.111 [-0.652, 0.688] | 0.170 [-1.257, 0.844] | 0.670 [0.080, 0.950] | 0.722 [0.203, 0.971] |
| 5 | ALL | 83 | 0.215 [-0.011, 0.429] | 0.280 [0.037, 0.489] | 0.326 [0.050, 0.540] |  |  |
| 6 | RB | 34 | 0.692 [0.443, 0.852] | 0.663 [0.474, 0.824] | 0.721 [0.497, 0.990] | 0.967 [0.906, 0.985] | 0.961 [0.887, 0.984] |
| 6 | WR | 34 | 0.052 [-0.373, 0.413] | 0.172 [-0.284, 0.531] | 0.264 [-0.434, 1.070] | 0.956 [0.887, 0.982] | 0.948 [0.866, 0.981] |
| 6 | TE | 10 | 0.221 [-0.508, 0.760] | 0.053 [-0.560, 0.560] | 0.119 [-0.994, 1.687] | 0.954 [0.753, 1.000] | 0.914 [0.599, 1.000] |
| 6 | ALL | 78 | 0.326 [0.108, 0.533] | 0.342 [0.136, 0.549] | 0.481 [0.178, 0.832] |  |  |
| 7 | RB | 36 | 0.618 [0.321, 0.838] | 0.532 [0.245, 0.799] | 0.319 [0.132, 0.704] | 0.939 [0.844, 0.978] | 0.929 [0.830, 0.974] |
| 7 | WR | 35 | 0.220 [-0.152, 0.544] | 0.315 [-0.015, 0.567] | 0.489 [-0.023, 1.081] | 0.960 [0.894, 0.984] | 0.960 [0.893, 0.985] |
| 7 | TE | 12 | 0.116 [-0.494, 0.627] | -0.070 [-0.447, 0.442] | -0.219 [-2.044, 1.017] | 0.958 [0.790, 1.000] | 0.967 [0.831, 0.998] |
| 7 | ALL | 83 | 0.388 [0.181, 0.568] | 0.347 [0.168, 0.537] | 0.332 [0.159, 0.615] |  |  |
| pooled | RB | 104 | 0.674 [0.462, 0.823] | 0.564 [0.379, 0.752] | 0.427 [0.257, 0.680] | 0.957 [0.901, 0.977] | 0.950 [0.883, 0.975] |
| pooled | WR | 105 | 0.057 [-0.257, 0.343] | 0.182 [-0.188, 0.474] | 0.262 [-0.291, 0.730] | 0.948 [0.891, 0.970] | 0.946 [0.886, 0.972] |
| pooled | TE | 35 | 0.056 [-0.334, 0.433] | 0.040 [-0.393, 0.392] | 0.083 [-0.778, 0.761] | 0.860 [0.580, 0.975] | 0.868 [0.581, 0.972] |
| pooled | ALL | 244 | 0.312 [0.117, 0.481] | 0.321 [0.157, 0.477] | 0.358 [0.177, 0.558] |  |  |

## 3. De-meaned move vs reception evidence (common set, pooled weeks; history players only)

| Pub | Pos | n | Sp. hist share | Sp. hist rec/g | Sp. ROS rec/g | slope on hist full-strength | slope on ROS full-strength | Pearson ROS full-strength |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbs | RB | 100 | 0.657 [0.400, 0.835] | 0.605 [0.383, 0.782] | 0.266 [-0.091, 0.544] | 0.589 [0.412, 0.764] | 0.157 [-0.007, 0.290] | 0.317 [-0.013, 0.578] |
| cbs | WR | 101 | 0.144 [-0.155, 0.408] | -0.459 [-0.670, -0.169] | -0.301 [-0.567, 0.008] | 0.312 [-0.079, 0.656] | 0.037 [-0.088, 0.168] | 0.080 [-0.173, 0.330] |
| cbs | TE | 35 | -0.063 [-0.415, 0.357] | -0.477 [-0.790, 0.061] | -0.405 [-0.607, -0.040] | -0.188 [-0.750, 0.328] | 0.017 [-0.192, 0.156] | 0.033 [-0.387, 0.268] |
| cbs | ALL | 236 | 0.319 [0.139, 0.472] | -0.114 [-0.322, 0.113] | -0.142 [-0.338, 0.061] | 0.358 [0.184, 0.551] | 0.062 [-0.017, 0.146] | 0.127 [-0.037, 0.283] |
| usatoday | RB | 100 | 0.761 [0.614, 0.845] | 0.652 [0.401, 0.788] | 0.293 [-0.029, 0.565] | 0.745 [0.526, 1.063] | 0.098 [-0.125, 0.279] | 0.136 [-0.141, 0.460] |
| usatoday | WR | 101 | 0.550 [0.270, 0.738] | 0.269 [-0.001, 0.508] | 0.190 [-0.094, 0.421] | 0.526 [0.287, 0.851] | 0.063 [0.006, 0.147] | 0.210 [0.024, 0.396] |
| usatoday | TE | 35 | 0.580 [0.183, 0.847] | 0.420 [-0.087, 0.803] | 0.146 [-0.439, 0.615] | 0.336 [0.058, 0.575] | 0.036 [-0.102, 0.216] | 0.143 [-0.435, 0.623] |
| usatoday | ALL | 236 | 0.655 [0.522, 0.757] | 0.444 [0.280, 0.582] | 0.222 [0.029, 0.393] | 0.600 [0.452, 0.801] | 0.066 [-0.001, 0.136] | 0.151 [-0.002, 0.315] |

cbs: rows 244, history fallback 8, no ROS games 16.

usatoday: rows 244, history fallback 8, no ROS games 16.

## 4. Reachable ceiling: within (mean RB/WR/TE Spearman, l_gate.metrics) on the common set

| Pub | Dir | Predictor | slope | within pooled | gain vs unchanged pooled | gain wk5 / wk6 / wk7 |
| --- | --- | --- | --- | --- | --- | --- |
| cbs | S_to_F | unchanged |  | 0.994 [0.981, 0.996] | 0.000 [0.000, 0.000] | +0.0000 / +0.0000 / +0.0000 |
| cbs | S_to_F | other_publisher_move_fitted_slope | 0.3581 | 0.996 [0.985, 0.997] | 0.002 [-0.007, 0.010] | +0.0038 / -0.0002 / +0.0018 |
| cbs | S_to_F | hist_full_strength_fitted_slope | 0.3582 | 0.992 [0.968, 0.996] | -0.002 [-0.018, 0.004] | -0.0000 / -0.0042 / -0.0004 |
| cbs | S_to_F | oracle_ros_fitted_slope | 0.062 | 0.992 [0.968, 0.995] | -0.002 [-0.018, 0.004] | -0.0052 / -0.0006 / -0.0009 |
| cbs | S_to_F | oracle_ros_slope_1 | 1.0 | 0.968 [0.915, 0.984] | -0.026 [-0.071, -0.008] | -0.0418 / -0.0225 / -0.0124 |
| cbs | F_to_S | unchanged |  | 0.994 [0.981, 0.996] | 0.000 [0.000, 0.000] | +0.0000 / +0.0000 / +0.0000 |
| cbs | F_to_S | other_publisher_move_fitted_slope | 0.3581 | 0.994 [0.975, 0.996] | -0.000 [-0.014, 0.008] | +0.0030 / -0.0042 / +0.0010 |
| cbs | F_to_S | hist_full_strength_fitted_slope | 0.3582 | 0.994 [0.977, 0.997] | 0.000 [-0.009, 0.007] | -0.0009 / -0.0002 / +0.0013 |
| cbs | F_to_S | oracle_ros_fitted_slope | 0.062 | 0.993 [0.973, 0.995] | -0.001 [-0.015, 0.006] | +0.0025 / -0.0050 / -0.0004 |
| cbs | F_to_S | oracle_ros_slope_1 | 1.0 | 0.961 [0.909, 0.976] | -0.033 [-0.082, -0.016] | -0.0202 / -0.0292 / -0.0484 |
| cbs | S_to_F | unchanged, own set | | 0.994 [0.981, 0.996] | | |
| usatoday | S_to_F | unchanged |  | 0.991 [0.971, 0.995] | 0.000 [0.000, 0.000] | +0.0000 / +0.0000 / +0.0000 |
| usatoday | S_to_F | other_publisher_move_fitted_slope | 0.2873 | 0.991 [0.968, 0.996] | -0.000 [-0.008, 0.006] | -0.0026 / +0.0002 / +0.0022 |
| usatoday | S_to_F | hist_full_strength_fitted_slope | 0.6001 | 0.992 [0.969, 0.996] | 0.001 [-0.006, 0.008] | -0.0014 / +0.0006 / +0.0040 |
| usatoday | S_to_F | oracle_ros_fitted_slope | 0.0657 | 0.988 [0.952, 0.995] | -0.004 [-0.023, 0.001] | -0.0048 / -0.0040 / -0.0020 |
| usatoday | S_to_F | oracle_ros_slope_1 | 1.0 | 0.938 [0.863, 0.966] | -0.053 [-0.115, -0.027] | -0.0741 / -0.0356 / -0.0494 |
| usatoday | F_to_S | unchanged |  | 0.991 [0.971, 0.995] | 0.000 [0.000, 0.000] | +0.0000 / +0.0000 / +0.0000 |
| usatoday | F_to_S | other_publisher_move_fitted_slope | 0.2873 | 0.989 [0.953, 0.995] | -0.003 [-0.023, 0.003] | -0.0027 / -0.0075 / +0.0020 |
| usatoday | F_to_S | hist_full_strength_fitted_slope | 0.6001 | 0.993 [0.973, 0.996] | 0.001 [-0.011, 0.015] | +0.0008 / -0.0006 / +0.0034 |
| usatoday | F_to_S | oracle_ros_fitted_slope | 0.0657 | 0.988 [0.946, 0.995] | -0.003 [-0.030, 0.005] | -0.0027 / -0.0032 / -0.0028 |
| usatoday | F_to_S | oracle_ros_slope_1 | 1.0 | 0.916 [0.794, 0.960] | -0.075 [-0.184, -0.030] | -0.0641 / -0.0805 / -0.0817 |
| usatoday | S_to_F | unchanged, own set | | 0.992 [0.979, 0.995] | | |

## 5. Half = (Standard + Full) / 2

| Pub | Week | n | max abs dev | share exact | share within 0.5 |
| --- | --- | --- | --- | --- | --- |
| cbs | 5 | 113 | 0.0 | 1.0 | 1.0 |
| cbs | 6 | 110 | 5.0 | 0.9818 | 0.9818 |
| cbs | 7 | 119 | 0.0 | 1.0 | 1.0 |
| usatoday | 5 | 261 | 0.5 | 0.7433 | 1.0 |
| usatoday | 6 | 262 | 1.0 | 0.7443 | 0.9885 |
| usatoday | 7 | 270 | 5.5 | 0.7481 | 0.9778 |

## Supplement: integer rounding and additive part (common set, mean of weekly values)

| Pub | Pos | var m (de-meaned) | integer-rounding var | share | F = a + bS: a, b | resid SD affine / flat mult | Sp. move vs log S |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cbs | RB | 0.003 | 0.0016 | 0.5556 | 0.2339, 1.0526 | 0.8701 / 0.8779 | 0.2378 |
| cbs | WR | 0.0046 | 0.001 | 0.2147 | 1.7665, 1.0649 | 1.0984 / 1.7876 | -0.7419 |
| cbs | TE | 0.0072 | 0.0021 | 0.2932 | 1.6226, 1.1045 | 0.8996 / 1.589 | -0.3542 |
| usatoday | RB | 0.0051 | 0.0003 | 0.0636 | 0.6093, 1.0506 | 1.8534 / 1.8865 | 0.0464 |
| usatoday | WR | 0.0022 | 0.0002 | 0.0818 | -0.8187, 1.0838 | 1.3504 / 1.3788 | 0.2505 |
| usatoday | TE | 0.0016 | 0.0003 | 0.1669 | -0.7361, 1.0871 | 1.0899 / 1.1238 | 0.1046 |

# Follow-up (items 6-7)

## 6. G2 'closer' ceiling (percentile move, common set)

pooled = mean of weekly statistics (as response_test.summarize); percentiles within position on the common set (l_gate scored set, all four columns > 0), not response_test's top-N set. Against ref=mean the method is half of the reference, which inflates corr and closer.

Unchanged (m = 0) has closer = 0 exactly.

Scale: mean r^2 of each publisher's own percentile move (the upper bound of closer) and share of players whose percentile move is exactly 0:

- cbs: RB 0.0007 (zero 0.3377), WR 0.0007 (zero 0.3706), TE 0.0016 (zero 0.465)
- usatoday: RB 0.0012 (zero 0.3965), WR 0.0012 (zero 0.3689), TE 0.002 (zero 0.5551)

| Cell | Pos | corr | slope | closer |
| --- | --- | --- | --- | --- |
| ref=cbs,method=usatoday | RB | 0.450 [0.171, 0.620] | 0.598 [0.248, 0.912] | -0.000 [-0.001, 0.000] |
| ref=cbs,method=usatoday | WR | 0.198 [-0.012, 0.378] | 0.270 [-0.023, 0.594] | -0.001 [-0.001, -0.000] |
| ref=cbs,method=usatoday | TE | -0.005 [-0.326, 0.341] | -0.042 [-0.524, 0.426] | -0.002 [-0.004, -0.001] |
| ref=cbs,method=usatoday | ALL | 0.269 [0.098, 0.415] | 0.344 [0.136, 0.530] | -0.001 [-0.001, -0.000] |
| ref=usatoday,method=cbs | RB | 0.450 [0.171, 0.620] | 0.343 [0.115, 0.508] | 0.000 [-0.000, 0.001] |
| ref=usatoday,method=cbs | WR | 0.198 [-0.012, 0.378] | 0.148 [-0.014, 0.310] | -0.000 [-0.001, 0.000] |
| ref=usatoday,method=cbs | TE | -0.005 [-0.326, 0.341] | 0.022 [-0.301, 0.522] | -0.002 [-0.003, -0.001] |
| ref=usatoday,method=cbs | ALL | 0.269 [0.098, 0.415] | 0.211 [0.067, 0.354] | -0.000 [-0.001, 0.000] |
| ref=mean,method=cbs | RB | 0.820 [0.624, 0.873] | 0.859 [0.605, 1.022] | 0.001 [0.000, 0.001] |
| ref=mean,method=cbs | WR | 0.713 [0.581, 0.812] | 0.815 [0.551, 1.113] | 0.000 [-0.000, 0.000] |
| ref=mean,method=cbs | TE | 0.650 [0.305, 0.878] | 0.889 [0.332, 1.515] | -0.000 [-0.001, 0.001] |
| ref=mean,method=cbs | ALL | 0.749 [0.645, 0.821] | 0.843 [0.667, 1.004] | 0.000 [0.000, 0.001] |
| ref=mean,method=usatoday | RB | 0.875 [0.774, 0.935] | 1.141 [0.978, 1.395] | 0.001 [0.000, 0.001] |
| ref=mean,method=usatoday | WR | 0.824 [0.682, 0.907] | 1.185 [0.887, 1.449] | 0.000 [-0.000, 0.000] |
| ref=mean,method=usatoday | TE | 0.743 [0.433, 0.874] | 1.111 [0.485, 1.668] | -0.000 [-0.001, 0.001] |
| ref=mean,method=usatoday | ALL | 0.837 [0.765, 0.886] | 1.157 [0.997, 1.333] | 0.000 [0.000, 0.001] |

## 7. Scale convention per column (mean of weeks 5-7; weekly values in the JSON)

| Pub | Pos | top-N value ratio F/S | all-listed value ratio | slope Std | slope Full | slope ratio F/S | proj ppg top-N ratio (pub top) | proj ppg top-N ratio (proj top) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cbs | RB | 1.0569 | 1.0655 | 3.2592 | 2.8697 | 0.8805 | 1.1949 | 1.2005 |
| cbs | WR | 1.1166 | 1.1597 | 4.8911 | 3.5601 | 0.7281 | 1.5492 | 1.5335 |
| cbs | TE | 1.2284 | 1.2387 | 4.0218 | 2.7569 | 0.6852 | 1.6524 | 1.6564 |
| usatoday | RB | 1.0604 | 1.0915 | 3.9103 | 3.4294 | 0.877 | 1.197 | 1.2005 |
| usatoday | WR | 1.0728 | 1.0673 | 5.7334 | 3.9987 | 0.6974 | 1.5397 | 1.5335 |
| usatoday | TE | 1.0684 | 1.066 | 5.8327 | 3.7661 | 0.6455 | 1.6469 | 1.6564 |

Top-N: 12 for RB and WR, 6 for TE. Slopes: OLS of chart value on mean projected ppg at that scoring (projection lines as l_gate loads them), players listed > 0 in both columns.

## 8. Test-retest vs cross-publisher (de-meaned move, common set in both weeks)

common set (l_gate scored set, all four columns > 0) in both weeks; de-meaned within position on the paired set; pooled stacks both pairs, player-clustered bootstrap.
Pairs: 151 player-week pairs.

| Cell | Weeks | Pos | n | Spearman | Pearson |
| --- | --- | --- | --- | --- | --- |
| self_cbs_w_vs_w+1 | 5->6 | RB | 33 | 0.879 [0.672, 0.989] | 0.860 [0.666, 0.976] |
| self_cbs_w_vs_w+1 | 5->6 | WR | 33 | 0.861 [0.650, 0.970] | 0.723 [0.406, 0.951] |
| self_cbs_w_vs_w+1 | 5->6 | TE | 10 | 0.847 [0.437, 0.990] | 0.859 [0.721, 0.965] |
| self_cbs_w_vs_w+1 | 5->6 | ALL | 76 | 0.860 [0.745, 0.942] | 0.791 [0.618, 0.926] |
| self_cbs_w_vs_w+1 | 6->7 | RB | 33 | 0.967 [0.913, 0.991] | 0.966 [0.928, 0.991] |
| self_cbs_w_vs_w+1 | 6->7 | WR | 32 | 0.832 [0.602, 0.963] | 0.720 [0.406, 0.947] |
| self_cbs_w_vs_w+1 | 6->7 | TE | 10 | 0.132 [-0.699, 0.922] | 0.172 [-0.606, 0.833] |
| self_cbs_w_vs_w+1 | 6->7 | ALL | 75 | 0.789 [0.606, 0.916] | 0.649 [0.386, 0.902] |
| self_cbs_w_vs_w+1 | pooled | RB | 66 | 0.888 [0.754, 0.941] | 0.915 [0.811, 0.976] |
| self_cbs_w_vs_w+1 | pooled | WR | 65 | 0.833 [0.571, 0.953] | 0.721 [0.373, 0.939] |
| self_cbs_w_vs_w+1 | pooled | TE | 20 | 0.486 [-0.091, 0.836] | 0.474 [-0.101, 0.863] |
| self_cbs_w_vs_w+1 | pooled | ALL | 151 | 0.824 [0.704, 0.910] | 0.717 [0.521, 0.898] |
| self_usatoday_w_vs_w+1 | 5->6 | RB | 33 | 0.916 [0.793, 0.968] | 0.887 [0.803, 0.971] |
| self_usatoday_w_vs_w+1 | 5->6 | WR | 33 | 0.913 [0.808, 0.963] | 0.833 [0.721, 0.936] |
| self_usatoday_w_vs_w+1 | 5->6 | TE | 10 | 0.735 [0.225, 0.978] | 0.655 [0.269, 0.959] |
| self_usatoday_w_vs_w+1 | 5->6 | ALL | 76 | 0.901 [0.839, 0.939] | 0.842 [0.767, 0.906] |
| self_usatoday_w_vs_w+1 | 6->7 | RB | 33 | 0.784 [0.511, 0.962] | 0.507 [0.201, 0.982] |
| self_usatoday_w_vs_w+1 | 6->7 | WR | 32 | 0.828 [0.593, 0.956] | 0.894 [0.764, 0.956] |
| self_usatoday_w_vs_w+1 | 6->7 | TE | 10 | 0.425 [-0.393, 1.000] | 0.540 [-0.455, 0.990] |
| self_usatoday_w_vs_w+1 | 6->7 | ALL | 75 | 0.774 [0.625, 0.893] | 0.605 [0.339, 0.938] |
| self_usatoday_w_vs_w+1 | pooled | RB | 66 | 0.847 [0.696, 0.933] | 0.631 [0.335, 0.946] |
| self_usatoday_w_vs_w+1 | pooled | WR | 65 | 0.866 [0.721, 0.932] | 0.856 [0.737, 0.922] |
| self_usatoday_w_vs_w+1 | pooled | TE | 20 | 0.573 [0.177, 0.802] | 0.606 [0.293, 0.855] |
| self_usatoday_w_vs_w+1 | pooled | ALL | 151 | 0.839 [0.756, 0.898] | 0.696 [0.480, 0.890] |
| cross_week_w_cbs_vs_usatoday | 5->6 | RB | 33 | 0.776 [0.579, 0.883] | 0.699 [0.578, 0.807] |
| cross_week_w_cbs_vs_usatoday | 5->6 | WR | 33 | -0.106 [-0.490, 0.294] | 0.150 [-0.434, 0.545] |
| cross_week_w_cbs_vs_usatoday | 5->6 | TE | 10 | -0.043 [-0.850, 0.749] | 0.011 [-0.762, 0.633] |
| cross_week_w_cbs_vs_usatoday | 5->6 | ALL | 76 | 0.259 [0.019, 0.473] | 0.319 [0.069, 0.538] |
| cross_week_w_cbs_vs_usatoday | 6->7 | RB | 33 | 0.677 [0.423, 0.845] | 0.649 [0.446, 0.815] |
| cross_week_w_cbs_vs_usatoday | 6->7 | WR | 32 | -0.016 [-0.394, 0.361] | 0.125 [-0.363, 0.530] |
| cross_week_w_cbs_vs_usatoday | 6->7 | TE | 10 | 0.221 [-0.521, 0.787] | 0.053 [-0.583, 0.548] |
| cross_week_w_cbs_vs_usatoday | 6->7 | ALL | 75 | 0.305 [0.068, 0.520] | 0.317 [0.068, 0.530] |
| cross_week_w_cbs_vs_usatoday | pooled | RB | 66 | 0.745 [0.549, 0.857] | 0.669 [0.535, 0.792] |
| cross_week_w_cbs_vs_usatoday | pooled | WR | 65 | -0.045 [-0.390, 0.314] | 0.138 [-0.370, 0.505] |
| cross_week_w_cbs_vs_usatoday | pooled | TE | 20 | -0.004 [-0.607, 0.508] | 0.027 [-0.651, 0.475] |
| cross_week_w_cbs_vs_usatoday | pooled | ALL | 151 | 0.287 [0.080, 0.485] | 0.316 [0.090, 0.517] |
| cross_week_w+1_cbs_vs_usatoday | 5->6 | RB | 33 | 0.722 [0.498, 0.866] | 0.686 [0.507, 0.841] |
| cross_week_w+1_cbs_vs_usatoday | 5->6 | WR | 33 | -0.032 [-0.419, 0.349] | 0.124 [-0.363, 0.533] |
| cross_week_w+1_cbs_vs_usatoday | 5->6 | TE | 10 | 0.221 [-0.553, 0.744] | 0.053 [-0.581, 0.546] |
| cross_week_w+1_cbs_vs_usatoday | 5->6 | ALL | 76 | 0.316 [0.088, 0.522] | 0.333 [0.099, 0.544] |
| cross_week_w+1_cbs_vs_usatoday | 6->7 | RB | 33 | 0.533 [0.210, 0.793] | 0.353 [0.107, 0.744] |
| cross_week_w+1_cbs_vs_usatoday | 6->7 | WR | 32 | 0.106 [-0.288, 0.459] | 0.253 [-0.150, 0.565] |
| cross_week_w+1_cbs_vs_usatoday | 6->7 | TE | 10 | 0.067 [-0.590, 0.650] | -0.061 [-0.440, 0.496] |
| cross_week_w+1_cbs_vs_usatoday | 6->7 | ALL | 75 | 0.281 [0.064, 0.474] | 0.232 [0.073, 0.469] |
| cross_week_w+1_cbs_vs_usatoday | pooled | RB | 66 | 0.594 [0.303, 0.791] | 0.465 [0.236, 0.767] |
| cross_week_w+1_cbs_vs_usatoday | pooled | WR | 65 | 0.047 [-0.287, 0.398] | 0.187 [-0.194, 0.522] |
| cross_week_w+1_cbs_vs_usatoday | pooled | TE | 20 | 0.064 [-0.312, 0.442] | -0.008 [-0.344, 0.316] |
| cross_week_w+1_cbs_vs_usatoday | pooled | ALL | 151 | 0.299 [0.091, 0.484] | 0.271 [0.097, 0.469] |
| self_cbs_w_vs_w+1_excl_carried_over | pooled | RB | 41 | 0.871 [0.674, 0.945] | 0.870 [0.697, 0.965] |
| self_cbs_w_vs_w+1_excl_carried_over | pooled | WR | 47 | 0.711 [0.403, 0.898] | 0.555 [0.177, 0.887] |
| self_cbs_w_vs_w+1_excl_carried_over | pooled | TE | 17 | 0.459 [-0.179, 0.861] | 0.452 [-0.178, 0.854] |
| self_cbs_w_vs_w+1_excl_carried_over | pooled | ALL | 105 | 0.721 [0.525, 0.870] | 0.603 [0.332, 0.851] |
| self_usatoday_w_vs_w+1_excl_carried_over | pooled | RB | 51 | 0.830 [0.660, 0.926] | 0.613 [0.316, 0.941] |
| self_usatoday_w_vs_w+1_excl_carried_over | pooled | WR | 48 | 0.835 [0.647, 0.918] | 0.838 [0.690, 0.913] |
| self_usatoday_w_vs_w+1_excl_carried_over | pooled | TE | 14 | 0.319 [-0.049, 0.739] | 0.398 [0.051, 0.696] |
| self_usatoday_w_vs_w+1_excl_carried_over | pooled | ALL | 113 | 0.811 [0.702, 0.882] | 0.663 [0.431, 0.886] |

| Pub | Pos | n | share identical move | share identical S and F |
| --- | --- | --- | --- | --- |
| cbs | RB | 66 | 0.5152 | 0.3788 |
| cbs | WR | 65 | 0.2769 | 0.2769 |
| cbs | TE | 20 | 0.15 | 0.15 |
| cbs | ALL | 151 | 0.3642 | 0.3046 |
| usatoday | RB | 66 | 0.3182 | 0.2273 |
| usatoday | WR | 65 | 0.3077 | 0.2615 |
| usatoday | TE | 20 | 0.35 | 0.3 |
| usatoday | ALL | 151 | 0.3179 | 0.2517 |
