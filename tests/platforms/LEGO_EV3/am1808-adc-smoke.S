/* SPDX-License-Identifier: MIT */
/* Original ARM926 proof: SPI0 CS3 -> ADS7957 manual N+2 conversion -> IRQ20.
 * Host injects raw channel6 and writes the expected10-bit code atffff1800.
 * The first two responses must name channel0; the third names channel6.
 */
.syntax unified
.cpu arm926ej-s
.arm
.equ ADC_SPI, 0x01c41000
.equ ADC_COMMAND, 0x00f71b40
.equ ADC_EXPECTED, 0xffff1800
.equ ADC_OBSERVED, 0xffff1804
.section .vectors, "ax"
.global _start
_start:
    b adc_reset
    b .
    b .
    b .
    b .
    b .
    b adc_irq
    b .
adc_reset:
    msr cpsr_c, #0xd2
    ldr sp, =0xffff1f00
    msr cpsr_c, #0xd3
    ldr sp, =0xffff1e00
    ldr r0, =0x01c10000
    ldr r1, [r0, #0xa10]
    bic r1, r1, #0x1f
    orr r1, r1, #3
    str r1, [r0, #0xa10]
    mov r1, #1
    str r1, [r0, #0x120]
    ldr r1, [r0, #0x810]
    and r1, r1, #0x1f
    cmp r1, #3
    bne adc_fail
    ldr r0, =ADC_SPI
    mov r1, #0
    str r1, [r0]
    mov r1, #1
    str r1, [r0]
    ldr r1, =0x00000e08 /* CS3,SOMI,SIMO,CLK functional pins */
    str r1, [r0, #0x14]
    ldr r1, =0x00009510 /* 150MHz /150 =1MHz,16bit */
    str r1, [r0, #0x50]
    ldr r1, =0x01000003
    str r1, [r0, #4]
    mov r4, #2
adc_prime:
    ldr r1, =ADC_COMMAND
    str r1, [r0, #0x3c]
    ldr r2, [r0, #0x40]
    tst r2, #0x80000000
    bne adc_fail
    ldr r3, =0x0000f003
    tst r2, r3
    bne adc_fail
    subs r4, r4, #1
    bne adc_prime
    /* Physical SPI0 event20, channel1/ARM IRQ. */
    ldr r0, =0xfffee414
    mov r1, #1
    str r1, [r0]
    ldr r0, =0xfffee028
    mov r1, #20
    str r1, [r0]
    ldr r0, =0xfffee034
    mov r1, #1
    str r1, [r0]
    ldr r0, =0xfffee010
    str r1, [r0]
    ldr r0, =ADC_SPI
    mov r1, #0x100
    str r1, [r0, #0x0c]
    str r1, [r0, #8]
    msr cpsr_c, #0x53
    ldr r1, =ADC_COMMAND
    str r1, [r0, #0x3c]
    ldr r8, =0x100000
adc_wait:
    subs r8, r8, #1
    bne adc_wait
    b adc_fail
adc_irq:
    ldr r0, =0xfffee904
    ldr r1, [r0]
    cmp r1, #20
    bne adc_fail
    ldr r0, =ADC_SPI
    ldr r1, [r0, #0x10]
    tst r1, #0x100
    beq adc_fail
    ldr r1, [r0, #0x40]
    ldr r0, =ADC_EXPECTED
    ldr r2, [r0]
    cmp r2, #1024
    bhs adc_fail
    mov r2, r2, lsl #2
    orr r2, r2, #0x6000
    cmp r1, r2
    bne adc_fail
    str r1, [r0, #4]
    ldr r0, =0xfffee024
    mov r1, #20
    str r1, [r0]
    ldr r1, =adc_ok
    b adc_print
adc_fail:
    ldr r1, =adc_bad
adc_print:
    ldr r0, =0x01d0c000
1:
    ldrb r2, [r1], #1
    cmp r2, #0
    beq 2f
    strb r2, [r0]
    b 1b
2:
    b 2b
adc_ok: .asciz "EV3 ADC SPI IRQ OK\n"
adc_bad: .asciz "EV3 ADC FAIL\n"
