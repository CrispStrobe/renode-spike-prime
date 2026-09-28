let lines = 0
bluetooth.startUartService()
bluetooth.onUartDataReceived(serial.delimiters(Delimiters.NewLine), function () {
    let s = bluetooth.uartReadUntil(serial.delimiters(Delimiters.NewLine))
    lines += 1
    bluetooth.uartWriteLine("echo " + s)
})
