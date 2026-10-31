"""Colab launcher wrapper."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "/content/app/backend")
os.chdir("/content/app/backend")

from app.colab_launch import main

main()
