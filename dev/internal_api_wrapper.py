#!/usr/bin/env python3
from multiprocessing import freeze_support
import bt_logging_patch
import internal_api
if __name__ == '__main__':
    freeze_support()
    internal_api.main()
