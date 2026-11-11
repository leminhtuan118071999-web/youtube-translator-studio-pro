"""Run inside the editor venv before Streamlit, without opening a browser."""
from .render_worker import recover_pending

if __name__ == '__main__':
    recovered = recover_pending()
    print(f'Đã tự khôi phục {len(recovered)} tác vụ V3 bị gián đoạn.', flush=True)
