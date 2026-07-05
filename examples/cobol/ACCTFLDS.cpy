01  ACCT-RECORD.
           05  ACCT-ID            PIC 9(8).
           05  ACCT-TYPE          PIC X(2).
           05  ACCT-BALANCE       PIC 9(11)V99.
           05  ACCT-FLAGS         PIC X(1)
                                   OCCURS 3 TIMES.
           05  ACCT-FLAG-REDEF    REDEFINES ACCT-FLAGS
                                   PIC 9(3).
           05  ACCT-STATUS        PIC X(1).
               88  ACTIVE-ACCT    VALUE "A".
               88  CLOSED-ACCT    VALUE "C".