
// This source code is subject to the terms of the Mozilla Public License 2.0 at https://mozilla.org/MPL/2.0/
// © Jimmyrockhard
 
//@version=4
study("Neo", overlay=true)


//Session Toggles
show_zerolag_ma= input(defval=true, title="fader") 
rainbowprc = input(close)
fmal_zl = input(1, "Rainbow Length 1")
smal_zl = input(1, "Rainbow Length 2")
showBuyTDs = input(true, title="Show TD Buy")
showSellTDs = input(true, title="Show TD Sell")

length_jma = input(title="JMA Smoothing Length", defval=7)
phase = input(title="JMA Smoothing Phase", step=0.01, defval=126)
power = input(title="JMA Smoothing Power", step=0.01,  defval=0.89144)
src_jma = input(title="JMA Smoothing Source", defval=close)
highlightMovements = input(title="Smoothing Highlight Movements ?", defval=true)


buySignals = 0
buySignals := (close < close[4]) ? buySignals[1] == 9 ? 1 : buySignals[1] + 1 : 0

sellSignals = 0
sellSignals := (close > close[4]) ? sellSignals[1] == 9 ? 1 : sellSignals[1] + 1 : 0

BuyOrSell = max(buySignals, sellSignals)

TD8buy = showBuyTDs and buySignals and BuyOrSell == 8
TD9buy = showBuyTDs and buySignals and BuyOrSell == 9

TD8sell = showSellTDs and sellSignals and BuyOrSell == 8
TD9sell = showSellTDs and sellSignals and BuyOrSell == 9


/////fader/////

tmal_zl = fmal_zl + smal_zl
Fmal_zl = smal_zl + tmal_zl
Ftmal_zl = tmal_zl + Fmal_zl
Smal_zl = Fmal_zl + Ftmal_zl
M1_zl = wma(rainbowprc, fmal_zl)
M2_zl = wma(M1_zl, smal_zl)
M3_zl = wma(M2_zl, tmal_zl)
M4_zl = wma(M3_zl, Fmal_zl)
M5_zl = wma(M4_zl, Ftmal_zl)
MAVW_zl = hma(M5_zl, Smal_zl)
phaseRatio = phase < -100 ? 0.5 : phase > 100 ? 2.5 : phase / 100 + 1.5
beta = 0.45 * (length_jma - 1) / (0.45 * (length_jma - 1) + 2)
alpha = pow(beta, power)
jma_2 = 0.0,e0 = 0.0,e1 = 0.0,e2 = 0.0
e0 := (1 - alpha) * src_jma + alpha * nz(e0[1])
e1 := (src_jma - e0) * (1 - beta) + beta * nz(e1[1])
e2 := (e0 + phaseRatio * e1 - nz(jma_2[1])) * pow(1 - alpha, 2) + pow(alpha, 2) * nz(e2[1])
jma_2 := e2 + nz(jma_2[1])
signal = (MAVW_zl + jma_2)/2
signalColor = highlightMovements ? (signal > signal[1] ? color.green : color.red) : #6d1e7f


plotshape(TD8buy, style=shape.labelup,text="8",color=color.green, textcolor=color.white, size=size.tiny, location=location.belowbar, transp=0)
plotshape(TD9buy, style=shape.labelup,text="9",color=color.green, textcolor=color.white, size=size.tiny, location=location.belowbar, transp=0)
plotshape(TD8sell, style=shape.labeldown,text="8",color=color.red, textcolor=color.white, size=size.tiny, location=location.abovebar, transp=0)
plotshape(TD9sell, style=shape.labeldown,text="9",color=color.red, textcolor=color.white, size=size.tiny, location=location.abovebar, transp=0)


// ALERTS /////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////

alertcondition(TD8buy, "TD 8 Buy", "TD 8 Buy") // Once per bar close
alertcondition(TD9buy, "TD 9 Buy", "TD 9 Buy") // Once per bar close
alertcondition(TD8sell, "TD 8 Sell", "TD 8 Sell") // Once per bar close
alertcondition(TD9sell, "TD 9 Sell", "TD 9 Sell") // Once per bar close

plot(show_zerolag_ma ? signal :na, color=signalColor, linewidth=3, transp=15)


/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
//*** ADX MOMENTUM CHANGE WARNINGS ***//
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
 
___adx___           = input(defval=true, title="| ADX Momentum Change Warnings |" )
 
//-------------------------------------------------------------------------//
//--- INPUTS
//-------------------------------------------------------------------------//
 
adxlen              = input(8, title="↳ ADX Smoothing")
dilen               = input(8, title="↳ DI Length")
thold               = input(10, title="↳ ADX Threshold", minval=-30, maxval=30)
 
//-------------------------------------------------------------------------//
//--- FUNCTIONS
//-------------------------------------------------------------------------//
 
dirmov(len) =>
    up = change(high)
    down = -change(low)
    truerange = rma(tr, len)
    plus = fixnan(100 * rma(up > down and up > 0 ? up : 0, len) / truerange)
    minus = fixnan(100 * rma(down > up and down > 0 ? down : 0, len) / truerange)
    [plus, minus]
 
adx(dilen, adxlen) =>
    [plus, minus] = dirmov(dilen)
    sum = plus + minus
    adx = 100 * rma(abs(plus - minus) / (sum == 0 ? 1 : sum), adxlen)
    [adx, plus, minus]
 
//-------------------------------------------------------------------------//
//--- CALCULATIONS
//-------------------------------------------------------------------------//
 
threshold           = thold
 
[sig_ini, up_ini, down_ini] = adx(dilen, adxlen)
 
sig                 = sig_ini - 30
up_adx              = up_ini - 30
down_adx            = down_ini - 30
 
sig_Slow            = sma(sig, 2)
 
crossover_1         = crossover(sig_Slow, sig)
b_color             = crossover(sig_Slow, sig) and sig > threshold and up_adx < down_adx ? color.green : crossover_1 and sig > threshold and up_adx > down_adx ? color.red : na
 
up_exit             = crossover_1 and sig > threshold and up_adx > down_adx
dn_exit             = crossover(sig_Slow, sig) and sig > threshold and up_adx < down_adx
 
//-------------------------------------------------------------------------//
//--- PLOTS
//-------------------------------------------------------------------------//
 
// bgcolor             (not ___adx___ ? na : b_color, title="Momentum Change Warnings", transp=70)
 
plotshape           (not ___adx___ ? na : up_exit, title="Up Warning", text="X︎", textcolor=color.black, style=shape.labeldown, size=size.normal, location=location.abovebar, color=color.yellow, transp=0)
plotshape           (not ___adx___ ? na : dn_exit, title="Down Warning", text="X︎", textcolor=color.black, style=shape.labelup, size=size.normal, location=location.belowbar, color=color.yellow, transp=0)
 
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// END OF SCRIPT
/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////


___3mlP___              = input(defval=true, title="| PREVIOUS 3-MONTHLY LEVELS |" )
 
p_openPrice3M           = security(syminfo.tickerid, '3M', open[1])
p_highPrice3M           = security(syminfo.tickerid, '3M', high[1])
p_lowPrice3M            = security(syminfo.tickerid, '3M', low[1])
p_closePrice3M          = security(syminfo.tickerid, '3M', close[1])
 
plot                    (not ___3mlP___ ? na : p_openPrice3M ? p_openPrice3M : na, title="Previous 3 Monthly Open",  linewidth=3, color=color.purple, transp=0, show_last=1, trackprice=true)
plot                    (not ___3mlP___ ? na : p_highPrice3M ? p_highPrice3M : na, title="Previous 3 Monthly High",  linewidth=1, color=color.purple, transp=10, show_last=1, trackprice=true)
plot                    (not ___3mlP___ ? na : p_lowPrice3M  ? p_lowPrice3M :  na, title="Previous 3 Monthly Low",  linewidth=1, color=color.purple, transp=10, show_last=1, trackprice=true)
plot                    (not ___3mlP___ ? na : p_closePrice3M ? p_closePrice3M :  na, title="Previous 3 Monthly Close",  linewidth=3, color=color.purple, transp=0, show_last=1, trackprice=true)
 
plotchar                (not ___3mlP___ ? na : p_openPrice3M, location=location.absolute, title="Previous 3 Monthly Open Label", textcolor=color.silver, show_last=1, text="P3M.O", offset=10, transp=20, char="⦁", color=color.silver)
plotchar                (not ___3mlP___ ? na : p_highPrice3M, location=location.absolute, title="Previous 3 Monthly High Label", textcolor=color.silver, show_last=1, text="P3M.H", offset=10, transp=20, char="⦁", color=color.silver)
plotchar                (not ___3mlP___ ? na : p_lowPrice3M, location=location.absolute, title="Previous 3 Monthly Low Label", textcolor=color.silver, show_last=1, text="P3M.L", offset=10, transp=20, char="⦁", color=color.silver)
plotchar                (not ___3mlP___ ? na : p_closePrice3M, location=location.absolute, title="Previous 3 Monthly Close Label", textcolor=color.silver, show_last=1, text="P3M.C", offset=10, transp=20, char="⦁", color=color.silver)
 

___ylP___               = input(defval=true, title="| PREVIOUS YEARLY LEVELS |" )
 
p_openPriceY            = security(syminfo.tickerid, '12M', open[1])
p_highPriceY            = security(syminfo.tickerid, '12M', high[1])
p_lowPriceY             = security(syminfo.tickerid, '12M', low[1])
p_closePriceY           = security(syminfo.tickerid, '12M', close[1])
 
plot                    (not ___ylP___ ? na : p_openPriceY ? p_openPriceY : na, title="Previous Yearly Open",  linewidth=2, color=color.silver, transp=0, show_last=1, trackprice=true)
plot                    (not ___ylP___ ? na : p_highPriceY ? p_highPriceY : na, title="Previous Yearly High",  linewidth=1, color=color.silver, transp=10, show_last=1, trackprice=true)
plot                    (not ___ylP___ ? na : p_lowPriceY ? p_lowPriceY :  na, title="Previous Yearly Low",  linewidth=1, color=color.silver, transp=10, show_last=1, trackprice=true)
plot                    (not ___ylP___ ? na : p_closePriceY ? p_closePriceY :  na, title="Previous Yearly Close",  linewidth=2, color=color.silver, transp=0, show_last=1, trackprice=true)
 
plotchar                (not ___ylP___ ? na : p_openPriceY, location=location.absolute, title="Previous Yearly Open Label", textcolor=color.silver, show_last=1, text="PY.O", offset=20, transp=20, char="⦁", color=color.silver)
plotchar                (not ___ylP___ ? na : p_highPriceY, location=location.absolute, title="Previous Yearly High Label", textcolor=color.silver, show_last=1, text="PY.H", offset=20, transp=20, char="⦁", color=color.silver)
plotchar                (not ___ylP___ ? na : p_lowPriceY, location=location.absolute, title="Previous Yearly Low Label", textcolor=color.silver, show_last=1, text="PY.L", offset=20, transp=20, char="⦁", color=color.silver)
plotchar                (not ___ylP___ ? na : p_closePriceY, location=location.absolute, title="Previous Yearly Close Label", textcolor=color.silver, show_last=1, text="PY.C", offset=20, transp=20, char="⦁", color=color.silver)
 

