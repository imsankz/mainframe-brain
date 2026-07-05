IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTMAST.
      *  Sample VSAM KSDS read + sequential report writer.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCOUNTS-FILE
               ASSIGN TO ACCTMAST
               ORGANIZATION  IS INDEXED
               ACCESS MODE  IS RANDOM
               RECORD KEY   IS ACCT-KEY
               ALTERNATE RECORD KEY IS ACCT-NAME.
           SELECT PAY-FILE
               ASSIGN TO PAYDATA
               ORGANIZATION  IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCOUNTS-FILE
           RECORDING MODE IS F.
       01  ACCOUNT-RECORD.
           05  ACCT-KEY          PIC X(8).
           05  ACCT-NAME          PIC X(24).
       FD  PAY-FILE.
       01  PAY-RECORD             PIC X(80).
       WORKING-STORAGE SECTION.
       01  WS-EOF                 PIC X VALUE 'N'.
       01  WS-LINE                PIC X(80) VALUE SPACES.
       PROCEDURE DIVISION.
       MAIN-PARA.
           OPEN I-O ACCOUNTS-FILE
           OPEN OUTPUT PAY-FILE.
       READ-LOOP.
           READ ACCOUNTS-FILE NEXT RECORD
               AT END
                   MOVE 'Y' TO WS-EOF
           END-READ.
       PROCESS-IT.
           IF ACCT-KEY = SPACES
               GO TO CLOSE-OUT
           END-IF.
           MOVE ACCOUNT-RECORD TO PAY-RECORD.
           WRITE PAY-RECORD.
           GO TO READ-LOOP.
       CLOSE-OUT.
           CLOSE ACCOUNTS-FILE PAY-FILE.
           STOP RUN.