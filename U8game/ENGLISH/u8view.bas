' U8VIEW.BAS - By: Michael De Piazzi
' You can use and modify any of this code, but please give my name a mention
' if you distribute it
DEFINT A-Z
CLEAR

GoTyp = 1: GoFrm = 3     ' Type and frame to display

IF DIR$("STATIC\U8PAL.PAL") = "" THEN PRINT "STATIC\U8PAL.PAL not found": CLEAR : END
IF DIR$("STATIC\U8SHAPES.FLX") = "" THEN PRINT "STATIC\U8SHAPES.FLX not found": CLEAR : END

DIM TypPos(0 TO 2047) AS LONG
DIM TypSiz(0 TO 2047) AS LONG
DIM FrmPos(0 TO 1549) AS LONG
DIM FrmSiz(0 TO 1549) AS LONG
DIM LinPos(0 TO 199) AS LONG

SCREEN 13
CLS
OPEN "STATIC\U8PAL.PAL" FOR BINARY AS #1
SEEK #1, 5
OUT &H3C8, 0
FOR Ct = 1 TO 768
 OUT &H3C9, ASC(INPUT$(1, #1))
NEXT Ct
CLOSE #1

OPEN "STATIC\U8SHAPES.FLX" FOR BINARY AS #1

GET #1, 85, NumTyp
IF GoTyp < 0 OR GoTyp > NumTyp - 1 THEN CLOSE #1: CLEAR : END
SEEK #1, 129
FOR Ct = 0 TO NumTyp - 1
 GET #1, , TypPos(Ct): TypPos(Ct) = TypPos(Ct) + 1
 GET #1, , TypSiz(Ct)
NEXT Ct

IF TypSiz(GoTyp) < 1 THEN CLOSE #1: CLEAR : END
SEEK #1, TypPos(GoTyp)
Unknown$ = INPUT$(4, #1)
GET #1, , NumFrm
IF GoFrm < 0 OR GoFrm > NumFrm - 1 THEN CLOSE #1: CLEAR : END
FOR Ct = 0 TO NumFrm - 1
 Tmp1 = ASC(INPUT$(1, #1)): Tmp2 = ASC(INPUT$(1, #1)): Tmp3 = ASC(INPUT$(1, #1))
 FrmPos(Ct) = 65536 * Tmp3 + 256& * Tmp2 + Tmp1 + TypPos(GoTyp)
 Unknown$ = INPUT$(1, #1)
 Tmp1 = ASC(INPUT$(1, #1)): Tmp2 = ASC(INPUT$(1, #1))
 FrmSiz(Ct) = 256& * Tmp2 + Tmp1
NEXT Ct

IF FrmSiz(GoFrm) < 1 THEN CLOSE #1: CLEAR : END
SEEK #1, FrmPos(GoFrm)
GET #1, , TypNum
GET #1, , FrmNum
Unknown$ = INPUT$(4, #1)
GET #1, , Compr
GET #1, , XLen
GET #1, , YLen
GET #1, , XOff
GET #1, , YOff
FOR Ct = 0 TO YLen - 1
 LinPos(Ct) = SEEK(1)
 Tmp1 = ASC(INPUT$(1, #1)): Tmp2 = ASC(INPUT$(1, #1))
 TmpPos& = Tmp2 * 256& + Tmp1
 LinPos(Ct) = LinPos(Ct) + TmpPos&
NEXT Ct

StXPos = 160 - XOff: StYPos = 150 - YOff
XPos = XLen: YPos = -1
DO
 DO UNTIL XPos < XLen
  YPos = YPos + 1
  IF YPos = YLen THEN EXIT DO
  SEEK #1, LinPos(YPos)
  XPos = ASC(INPUT$(1, #1))
 LOOP
 IF YPos = YLen THEN EXIT DO
 DatLen = ASC(INPUT$(1, #1))
 IF Compr = 1 THEN
  IF (DatLen AND 1) = 1 THEN
   DatLen = DatLen \ 2
   LINE (XPos + StXPos, YPos + StYPos)-(XPos + DatLen - 1 + StXPos, YPos + StYPos), ASC(INPUT$(1, #1))
  ELSE
   DatLen = DatLen \ 2
   FOR CtX = XPos TO XPos + DatLen - 1
    PSET (CtX + StXPos, YPos + StYPos), ASC(INPUT$(1, #1))
   NEXT CtX
  END IF
 ELSE
  FOR CtX = XPos TO XPos + DatLen - 1
   PSET (CtX + StXPos, YPos + StYPos), ASC(INPUT$(1, #1))
  NEXT CtX
 END IF
 XPos = XPos + DatLen
 IF XPos < XLen THEN XPos = XPos + ASC(INPUT$(1, #1))
LOOP

CLOSE #1
CLEAR
END