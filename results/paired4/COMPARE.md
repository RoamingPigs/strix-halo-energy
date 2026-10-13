# ROCm against Vulkan

Ratio is ROCm over Vulkan (mean over repeats). 'overlap' means the repeat ranges overlap, so no claim.

| Cell | tok/s | wall W | package W | wall net J/tok |
|---|---|---|---|---|
| gemma4-12b-q4@16384 | 0.968 (lower; n 3/3) | 0.928 (lower; n 3/3) | 0.899 (lower; n 3/3) | 0.948 (overlap; n 3/3) |
| gemma4-12b-q4@32768 | 0.965 (lower; n 3/3) | 1.009 (overlap; n 3/3) | 0.986 (lower; n 3/3) | 1.033 (higher; n 3/3) |
| gemma4-12b-q4@4096 | 0.969 (lower; n 3/3) | 0.950 (lower; n 3/3) | 0.913 (lower; n 3/3) | 0.967 (lower; n 3/3) |
| gemma4-12b-q4@64 | 0.984 (lower; n 3/3) | 0.942 (lower; n 3/3) | 0.909 (lower; n 3/3) | 0.940 (lower; n 3/3) |
| gemma4-26b-a4b-q4@16384 | 0.933 (lower; n 3/3) | 1.028 (higher; n 3/3) | 1.023 (higher; n 3/3) | 0.985 (overlap; n 3/3) |
| gemma4-26b-a4b-q4@32768 | 0.959 (lower; n 3/3) | 1.029 (higher; n 3/3) | 1.025 (higher; n 3/3) | 0.971 (lower; n 3/3) |
| gemma4-26b-a4b-q4@4096 | 0.902 (lower; n 3/3) | 0.993 (overlap; n 3/3) | 0.988 (overlap; n 3/3) | 0.971 (overlap; n 3/3) |
| gemma4-26b-a4b-q4@64 | 0.919 (lower; n 3/3) | 0.941 (lower; n 3/3) | 0.928 (lower; n 3/3) | 0.938 (lower; n 3/3) |
| qwen35-9b-q4km@16384 | 0.977 (lower; n 3/3) | 1.104 (higher; n 3/3) | 1.088 (higher; n 3/3) | 1.111 (higher; n 3/3) |
| qwen35-9b-q4km@32768 | 0.990 (lower; n 3/3) | 1.083 (higher; n 3/3) | 1.069 (higher; n 3/3) | 1.083 (higher; n 3/3) |
| qwen35-9b-q4km@4096 | 0.971 (lower; n 3/3) | 1.169 (higher; n 3/3) | 1.166 (higher; n 3/3) | 1.197 (higher; n 3/3) |
| qwen35-9b-q4km@64 | 0.978 (lower; n 3/3) | 1.148 (higher; n 3/3) | 1.150 (higher; n 3/3) | 1.168 (higher; n 3/3) |
| qwen36-35b-a3b-q8@16384 | 0.906 (lower; n 3/3) | 0.886 (lower; n 3/3) | 0.852 (lower; n 3/3) | 0.918 (lower; n 3/3) |
| qwen36-35b-a3b-q8@32768 | 0.936 (lower; n 3/3) | 0.924 (lower; n 3/3) | 0.885 (lower; n 3/3) | 0.936 (lower; n 3/3) |
| qwen36-35b-a3b-q8@4096 | 0.891 (lower; n 3/3) | 0.886 (lower; n 3/3) | 0.844 (lower; n 3/3) | 0.931 (lower; n 3/3) |
| qwen36-35b-a3b-q8@64 | 0.881 (lower; n 3/3) | 0.869 (lower; n 3/3) | 0.832 (lower; n 3/3) | 0.925 (lower; n 3/3) |
