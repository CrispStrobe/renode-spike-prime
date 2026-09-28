/* SPDX-License-Identifier: MIT */
ENTRY(_start)
SECTIONS
{
    . = 0;
    .text : { KEEP(*(.vectors)) *(.text*) }
    .rodata : { *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
}
