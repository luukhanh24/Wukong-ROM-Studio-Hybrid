@echo off
TITLE Wukong Flashing Tool
chcp 65001 >nul
cd %~dp0
set fastboot=bin\windows\fastboot.exe
set adb=bin\windows\adb.exe
set CHECKSUM_FILE=wukong_md5_hashes.txt
set INFO_FILE=info.txt
set SEARCH_DIRS=images firmware-update
set error_count=0
set rec=0
if not exist %fastboot% echo %fastboot% not found. & pause & exit /B 1
if not exist %adb% echo %adb% not found. & pause & exit /B 1
if not exist %CHECKSUM_FILE% echo %CHECKSUM_FILE% not found. & pause & exit /B 1
if not exist %INFO_FILE% echo %INFO_FILE% not found. & pause & exit /B 1
set "Devices=" & set "Version=" & set "Region=" & set "WK=" & set "WK_ver="
for /f "tokens=1* delims=:" %%a in ('findstr /n "^" "%INFO_FILE%"') do (
    if "%%a"=="1" set "Devices=%%b"
    if "%%a"=="2" set "Version=%%b"
    if "%%a"=="3" set "Region=%%b"
    if "%%a"=="4" set "WK=%%b"
    if "%%a"=="5" set "WK_ver=%%b"
)
echo.
echo [97;41m                                                              [0m
echo [97;41m   .d88b.  d8b   db d88888b d8888b. db      db    db .d8888.  [0m
echo [97;41m  .8P  Y8. 888o  88 88'     88  `8D 88      88    88 88'  YP  [0m
echo [97;41m  88    88 88V8o 88 88ooooo 88oodD' 88      88    88 `8bo.    [0m
echo [97;41m  88    88 88 V8o88 88~~~~~ 88~~~   88      88    88   `Y8b.  [0m
echo [97;41m  `8b  d8' 88  V888 88.     88      88booo. 88b  d88 db   8D  [0m
echo [97;41m   `Y88P'  VP   V8P Y88888P 88      Y88888P ~Y8888P' `8888Y'  [0m
echo [97;41m                                                              [0m
echo [30;107m=========================== Wukong ===========================[0m
echo [30;107m  Author: https://t.me/Kswukong                               [0m
echo [30;107m  Support group: https://t.me/OnePlus_Ace5_Port               [0m
echo.
echo.
echo.


echo Devices : %Devices%
echo Version : %Version%
echo Region  : %Region%
echo Wukong  %WK%  %WK_ver%
echo.

echo [96m1. Check path.[0m
echo Working dir: %CD%
if not "%CD%"=="%CD: =%" (
    echo [91m[!] Warning: The current path contains spaces.[0m
) else (
    echo [92m[OK] Done.[0m
)

echo [96m2. Check image file integrity.[0m
echo Please wait.
set /a progress_total=0
for /f "usebackq tokens=1,*" %%a in ("%CHECKSUM_FILE%") do set /a progress_total+=1
set /a progress_current=0
echo Files to verify: %progress_total%
for /f "tokens=1,*" %%a in ('type "%CHECKSUM_FILE%"') do (
    call :checkFile "%%a" "%%b"
)
echo.
if %error_count% equ 0 (
    echo [92m[OK] Done.[0m
) else (
    echo [91m[!] Warning: Detected %error_count% corrupt or missing file[0m
    pause
    exit
)

echo [96m3. Check bootloader status.[0m
echo Waiting for device...
:wait_bootloader
%fastboot% getvar is-userspace 2>&1 | findstr /r /x /c:"is-userspace: no$" >nul && (
	echo [92m[OK] Your device is currently in Bootloader mode.[0m
	goto :done
) || (
	echo [91m[!] Your device is currently in FastbootD mode.[0m
	%fastboot% reboot bootloader
    timeout /t 5 >nul
	goto :wait_bootloader
)
:done

echo.
echo --------------------------------------------------------
echo #   y = Format data      #   n = Keep data             #
echo --------------------------------------------------------
set /p format=Your choice (y/n): 
echo.
echo --------------------------------------------------------
echo #   y = Flash firmware   #   n = Skip firmware image   #
echo --------------------------------------------------------
set /p firmware=Your choice (y/n): 
echo.

if exist "images\OrangeFox.img" (
    %fastboot% flash recovery_a images\OrangeFox.img || echo [91m[!] Flash OrangeFox error[0m && pause && exit
	%fastboot% flash recovery_b images\OrangeFox.img || echo [91m[!] Flash OrangeFox error[0m && pause && exit
) else (
    if exist "images\TWRP.img" (
        %fastboot% flash recovery_a images\TWRP.img || echo [91m[!] Flash TWRP error[0m && pause && exit
		%fastboot% flash recovery_b images\TWRP.img || echo [91m[!] Flash TWRP error[0m && pause && exit
    ) else (
        echo Neither OrangeFox.img nor TWRP.img was found in the images folder.
		set /a rec+=1
    )
)
if /i "%firmware%"=="y" (
	%fastboot% reboot fastboot
	echo.
	timeout 15 /nobreak
	echo.

	for %%G in ("firmware-update\*.img") do (
		%fastboot% flash --slot=all "%%~nG" "%%~fG" || echo [91m[!] Flash %%~nG error[0m && pause && exit
	)
)	
%fastboot% flash vbmeta_a images\vbmeta.img || echo [91m[!] Flash vbmeta error[0m && pause && exit
%fastboot% flash vbmeta_b images\vbmeta.img || echo [91m[!] Flash vbmeta error[0m && pause && exit
%fastboot% flash vbmeta_system_a images\vbmeta_system.img || echo [91m[!] Flash vbmeta_system error[0m && pause && exit
%fastboot% flash vbmeta_system_b images\vbmeta_system.img || echo [91m[!] Flash vbmeta_system error[0m && pause && exit
%fastboot% flash vbmeta_vendor_a images\vbmeta_vendor.img || echo [91m[!] Flash vbmeta_vendor error[0m && pause && exit
%fastboot% flash vbmeta_vendor_b images\vbmeta_vendor.img || echo [91m[!] Flash vbmeta_vendor error[0m && pause && exit
%fastboot% flash dtbo_a images\dtbo.img || echo [91m[!] Flash dtbo error[0m && pause && exit
%fastboot% flash dtbo_b images\dtbo.img || echo [91m[!] Flash dtbo error[0m && pause && exit
%fastboot% flash boot_a images\boot.img || echo [91m[!] Flash boot error[0m && pause && exit
%fastboot% flash boot_b images\boot.img || echo [91m[!] Flash boot error[0m && pause && exit
%fastboot% flash init_boot_a images\init_boot.img || echo [91m[!] Flash init_boot error[0m && pause && exit
%fastboot% flash init_boot_b images\init_boot.img || echo [91m[!] Flash init_boot error[0m && pause && exit
%fastboot% flash vendor_boot_a images\vendor_boot.img || echo [91m[!] Flash vendor_boot error[0m && pause && exit
%fastboot% flash vendor_boot_b images\vendor_boot.img || echo [91m[!] Flash vendor_boot error[0m && pause && exit
if %rec% equ 1 (
	%fastboot% flash recovery_a images\recovery.img || echo [91m[!] Flash recovery error[0m && pause && exit
	%fastboot% flash recovery_b images\recovery.img || echo [91m[!] Flash recovery error[0m && pause && exit
)
if /i "%format%"=="y" if /i "%firmware%"=="y" (
	%fastboot% erase frp || echo [91m[!] Erase frp error[0m && pause && exit
)	
if /i "%firmware%"=="y" (
	%fastboot% reboot bootloader
	echo.
	timeout 15 /nobreak
	echo.
	%fastboot% flash modem_a images\modem.img || echo [91m[!] Flash modem error[0m && pause && exit
	%fastboot% flash modem_b images\modem.img || echo [91m[!] Flash modem error[0m && pause && exit
)

if /i "%format%"=="y" if /i "%firmware%"=="n" (
	%fastboot% reboot fastboot
	echo.
	timeout 15 /nobreak
	echo.
    %fastboot% erase frp
	%fastboot% reboot bootloader
	echo.
	timeout 15 /nobreak
	echo.
)
%fastboot% erase super || echo [91m[!] Erase super error[0m && pause && exit
%fastboot% flash super images\super.img || echo [91m[!] Flash super error[0m && pause && exit
%fastboot% set_active a
echo.
if /i "%format%"=="y" (
    echo Formatting system, please wait.
    %fastboot% -w
	%fastboot% reboot
	echo FLASHING DONE !!!
) else (
	if %rec% equ 0 (
		echo Wipe cache, please wait.
		%fastboot% reboot recovery
		timeout 60 /nobreak
		:wait_recovery
		%adb% devices | findstr /i "recovery" >nul
		if %errorlevel%==0 (
			echo [92m[OK] Your device is currently in Recovery mode.[0m
			goto :continue
		) else (
			timeout /t 5 >nul
			goto :wait_recovery
		)
		:continue
		%adb% shell rm -rf /data/cache/* /data/resource-cache/* /data/system/package_cache/* /data/dalvik-cache/arm/* /data/dalvik-cache/arm64/* /data/data/*/app_track_sslcache/* /data/data/*/app_pccache/* /data/data/*/app_tmpcache/* /data/data/*/cache/* /data/data/*/app_cache/* /data/data/*/code_cache/* /data/user_de/*/*/cache/* /data/user_de/*/*/code_cache/* /data/system/dropbox/* 2>/dev/null

		echo Keep data.
		%adb% reboot
		echo FLASHING DONE !!!
	)	
)
echo.
pause
exit


:checkFile
set "stored_md5=%~1"
set "filename=%~2"
set "found_path="
set /a progress_current+=1
call :showProgress "CHECK" "%filename%"
for %%d in (%SEARCH_DIRS%) do (
    if exist "%%d\%filename%" (
        set "found_path=%%d\%filename%"
        goto :FileFound
    )
)
:FileFound
if not defined found_path (
    set /a error_count+=1
    call :showProgress "MISSING" "%filename%"
    echo.
    goto :eof
)
set "current_md5="
for /f "tokens=*" %%h in ('certutil -hashfile "%found_path%" MD5 ^| findstr /v "hash CertUtil"') do (
    set "current_md5=%%h"
)
set "current_md5=%current_md5: =%"
if not "%stored_md5%" == "%current_md5%" (
    set /a error_count+=1
    call :showProgress "FAILED" "%filename%"
    echo.
) else (
    call :showProgress "OK" "%filename%"
)
goto :eof


:showProgress
setlocal EnableDelayedExpansion
set /a progress_percent=progress_current*100/progress_total
set /a progress_filled=(progress_current*20+progress_total-1)/progress_total
set "progress_bar="
for /l %%p in (1,1,20) do (
    if %%p leq !progress_filled! (
        set "progress_bar=!progress_bar!#"
    ) else (
        set "progress_bar=!progress_bar!-"
    )
)
if /i "%~1"=="OK" (
    <nul set /p "=[2K[1G[92m[!progress_bar!] !progress_percent!%% ^(!progress_current!/!progress_total!^) [OK] %~2[0m"
) else if /i "%~1"=="CHECK" (
    <nul set /p "=[2K[1G[96m[!progress_bar!] !progress_percent!%% ^(!progress_current!/!progress_total!^) [CHECK] %~2[0m"
) else (
    <nul set /p "=[2K[1G[91m[!progress_bar!] !progress_percent!%% ^(!progress_current!/!progress_total!^) [%~1] %~2[0m"
)
endlocal
goto :eof
