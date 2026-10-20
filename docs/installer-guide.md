# Installer Guide

## Silent install
`CLIConductor-Setup-0.1.0.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`

## Silent uninstall
`%LOCALAPPDATA%\Programs\CLIConductor\unins000.exe /VERYSILENT /SUPPRESSMSGBOXES`

## PATH
User PATH appended with install dir; removed on uninstall.

## SmartScreen
Unsigned installer shows "Windows protected your PC". Click More info -> Run anyway. Signing available via env vars.