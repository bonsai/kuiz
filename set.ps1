cd C:\Users\dance\zone\kihon\V3

# さっきダウンロードした JSON のパスに置き換え
$env:QUIZ_FIRESTORE_CREDENTIALS = "C:\Users\dance\kuiz-ebfe2-service-account.json"

.\run.ps1 -NoInstall