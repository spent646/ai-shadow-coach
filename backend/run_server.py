import multiprocessing as mp

def main():
    try:
        mp.freeze_support()
    except Exception:
        pass

    try:
        mp.set_start_method("spawn", force=True)
    except Exception:
        pass

    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8010, log_level="info")

if __name__ == "__main__":
    main()
