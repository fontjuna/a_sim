import PyInstaller.__main__

def build():
    """분할 빌드를 위한 스크립트"""
    opts = [
        'aaa.py',
        '--onedir',            
        '--clean',            
        '--noconfirm',         
        '--distpath=../dist',                       # 빌드 결과물 저장 경로
        '--workpath=../build',                      # 빌드 작업 경로
        '--specpath=../spec',                       # spec 파일 저장 경로
        '--add-data=../aaa/resources/aaa.ui;resources',    # --add-data=소스파일경로;대상폴더경로
        '--add-data=../aaa/resources/aaa.ico;resources',
        '--add-data=../aaa/images/*;images',               # 이미지 폴더
        '--icon=../aaa/resources/aaa.ico',                 # 아이콘 파일
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=PyQt5.QAxContainer',  # 추가: QAxWidget을 위한 모듈
        '--hidden-import=win32com',            # 추가: COM 통신 관련 모듈 
        '--hidden-import=pythoncom',           # 추가: PythonCOM 모듈
        '--hidden-import=tabulate',            # 추가: tabulate 모듈
        '--name=liberanimo',                               # 실행 파일 이름
    ]
    
    PyInstaller.__main__.run(opts)

if __name__ == "__main__":
    build()
