@echo off
setlocal
cd %~dp0

REM --- CAU HINH ---
set "OUTPUT_FILE=wukong_md5_hashes.txt"

REM Danh sach cac thu muc can quet (cach nhau boi dau cach)
REM Ban co the them folder khac vao sau neu muon
set "TARGET_FOLDERS=images firmware-update"

REM Loai tep can quet (*.img hoac *.* de lay tat ca)
REM Luu y: Thu muc firmware-update thuong chua ca file .bin, .mbn nen de *.* la tot nhat
set "FILE_PATTERN=*.*"
REM --- KET THUC CAU HINH ---

REM Xoa tep ket qua cu neu ton tai
if exist "%OUTPUT_FILE%" del "%OUTPUT_FILE%"

echo Dang bat dau tao ma MD5...
echo ---------------------------------------------------

REM --- VONG LAP CHINH: DUYET QUA TUNG THU MUC ---
for %%d in (%TARGET_FOLDERS%) do (
    if exist "%%d" (
        echo [+] Dang xu ly thu muc: "%%d"
        
        REM Duyet qua tat ca cac file trong thu muc do
        for %%f in ("%%d\%FILE_PATTERN%") do (
            echo     - Dang hash: %%~nxf
            
            REM Tinh toan MD5
            for /f "tokens=*" %%h in ('certutil -hashfile "%%f" MD5 ^| findstr /v "hash CertUtil"') do (
                REM Ghi vao file: [Ma Hash]  [Ten Tep]
                echo %%h  %%~nxf >> "%OUTPUT_FILE%"
            )
        )
    ) else (
        echo [!] Canh bao: Khong tim thay thu muc "%%d" (Bo qua)
    )
)

echo.
echo ---------------------------------------------------
if exist "%OUTPUT_FILE%" (
    echo HOAN TAT! Ket qua da duoc luu tai: %OUTPUT_FILE%
) else (
    echo KHONG CO FILE NAO DUOC TAO (Kiem tra lai cac thu muc).
)
echo.
pause