#!/usr/bin/env python3
"""DPO-only compatibility entrypoint. Legacy nine-slot writer prompt removed.

Delegates to the DPO four-section compiler while preserving original CLI name.
"""
from build_dpo_prompt import main

if __name__ == "__main__":
    main()
