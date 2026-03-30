<?php
// trigger.php — kicks off the UNAS fetch+translate job in background
// Assumes:
// - Project root is this file's directory
// - Virtualenv at .venv
// - Script at python-sync/tools/fetch_and_translate_unas.py
// - .env lives in project root

$root = realpath(__DIR__);
$script = $root . DIRECTORY_SEPARATOR . 'python-sync' . DIRECTORY_SEPARATOR . 'tools' . DIRECTORY_SEPARATOR . 'fetch_and_translate_unas.py';

// Log file to capture stdout/stderr from the run
$log = $root . DIRECTORY_SEPARATOR . 'trigger.log';

// Resolve python path (prefer venv; fall back to system python3)
if (stripos(PHP_OS_FAMILY, 'Windows') === 0) {
    $venvPy = $root . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR . 'Scripts' . DIRECTORY_SEPARATOR . 'python.exe';
    $python = file_exists($venvPy) ? $venvPy : 'python';
    // Background run via start /B; stderr/stdout to log
    $cmd = 'cmd /c start /B "" ' . escapeshellarg($python) . ' ' . escapeshellarg($script)
        . ' --max-items 1000 --page-limit 50 --delay 0 --resume >> ' . escapeshellarg($log) . ' 2>&1';
} else {
    $venvPy = $root . DIRECTORY_SEPARATOR . '.venv' . DIRECTORY_SEPARATOR . 'bin' . DIRECTORY_SEPARATOR . 'python';
    $python = file_exists($venvPy) ? $venvPy : '/usr/bin/python3';
    // Background run via &; stderr/stdout to log
    $cmd = escapeshellcmd($python) . ' ' . escapeshellarg($script)
        . ' --max-items 1000 --page-limit 50 --delay 0 --resume >> ' . escapeshellarg($log) . ' 2>&1 &';
}

// Kick it off
exec($cmd);
echo "Started background sync. Command: $cmd\nLog: $log\n";
