# frame_processor.py

    ## Description
    Image preprocessing

    ## Files it interacts with
    - data_pipeline/datasets/*  
- ml_training/training/*

    ## How it interacts
    - Consumes/produces SDK **events** where applicable.
    - Reads config from **sdk/config.py** (paths, plugins).
    - Uses **sdk/ids.py** for ULIDs and timestamps when emitting events or logs.
    - Emits structured logs via **sdk/logging.py** or project logger.

    ## Inputs / Outputs
    - Inputs: (to be detailed during implementation)
    - Outputs: (to be detailed during implementation)

    ## Extension points
    - Replaceable via the registry (where a contract exists).
    - Unit tests in `tests/` should validate behavior.

    ## Notes
    - Keep dependencies minimal; prefer interfaces over concrete imports.
