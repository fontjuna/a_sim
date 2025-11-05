import PyInstaller.__main__
import os

def build():
    """분할 빌드를 위한 스크립트"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    spec_path = os.path.join(base_dir, "spec")
    if not os.path.exists(spec_path):
        os.makedirs(spec_path)

    opts = [
        'aaa.py',
        '--onedir',            
        '--clean',            
        '--noconfirm',         
        '--distpath=D:/Exec/dist',                   # 빌드 결과물 저장 경로
        '--workpath=D:/Exec/build',                  # 빌드 작업 경로
        '--specpath=spec',                           # spec 파일 저장 경로
        f'--add-data={os.path.join(base_dir, "resources", "aaa.ui")};resources',     # --add-data=소스파일경로;대상폴더경로
        f'--add-data={os.path.join(base_dir, "resources", "aaa.ico")};resources',
        f'--add-data={os.path.join(base_dir, "images")}\\*;images',                # 이미지 폴더
        f'--add-data={os.path.join(base_dir, "script")};script',                  # script 폴더 전체 포함
        f'--icon={os.path.join(base_dir, "resources", "aaa.ico")}',                  # 아이콘 파일
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=PyQt5.QAxContainer',        # 추가: QAxWidget을 위한 모듈
        '--hidden-import=win32com',                  # 추가: COM 통신 관련 모듈 
        '--hidden-import=pythoncom',                 # 추가: PythonCOM 모듈
        '--hidden-import=tabulate',                  # 추가: tabulate 모듈
        '--name=liberanimo',                         # 실행 파일 이름
    ]
    
    PyInstaller.__main__.run(opts)

if __name__ == "__main__":
    build()
