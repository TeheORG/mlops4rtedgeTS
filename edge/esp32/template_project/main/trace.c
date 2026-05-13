#include "trace.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include <inttypes.h>
#include <stdio.h>

static const uart_port_t s_uart = UART_NUM_0;

void trace_init(int baud_rate)
{
    uart_config_t cfg = {
        .baud_rate  = baud_rate,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE
    };
    uart_param_config(s_uart, &cfg);
    uart_set_pin(s_uart,
                 UART_PIN_NO_CHANGE,
                 UART_PIN_NO_CHANGE,
                 UART_PIN_NO_CHANGE,
                 UART_PIN_NO_CHANGE);
    uart_driver_install(s_uart, 4096, 4096, 0, NULL, 0);
}

void trace_emit(uint32_t ev,
                        int32_t  model,
                        uint64_t tu,
                        uint64_t a,
                        uint64_t b,
                        uint64_t c)
{
    static uint32_t trace_drops = 0;
    // Timestamp en microsegundos (monótono, 64-bit)
    uint64_t ts = esp_timer_get_time();

    char buf[160];
    int len = snprintf(buf, sizeof(buf),
        "%" PRIu64 ",%" PRIu32 ",%" PRId32 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 "\n",
        ts, ev, model, tu, a, b, c);

    if (len > 0) {
        size_t free;
        uart_get_tx_buffer_free_size(s_uart, &free);

        if (free >= (size_t)len) {
            uart_write_bytes(s_uart, buf, len);
        } else {
            trace_drops++;
        }
    }
}
