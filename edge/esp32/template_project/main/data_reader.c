#include "data_reader.h"
#include "config.h"
#include <stdlib.h>
#if USE_SERIAL_READER
#include "driver/uart.h"
#include <string.h>
size_t read_events(event_t *buffer, size_t max_count)
{
    char buf[1024];
    int len = uart_read_bytes(
        UART_NUM_0,
        (uint8_t *)buf,              // <-- SIEMPRE bytes
        sizeof(buf) - 1,
        pdMS_TO_TICKS(10)             // timeout corto (polling)
    );
    if (len <= 0) {
        return 0;
    }
    buf[len] = '\0';                 // asegurar string válida
    size_t count = 0;
    char *tok = strtok(buf, ",\n");  // incluye '\n' por seguridad
    while (tok && count < max_count) {
        buffer[count++] = (event_t)strtol(tok, NULL, 10);
        tok = strtok(NULL, ",\n");
    }
    return count;
}

size_t read_events_old(event_t *buffer, size_t max_count) {
    //event_t buf[1024];
    char  buf[1024];
    int len = uart_read_bytes(UART_NUM_0, (event_t*)buf, sizeof(buf)-1, 10);
    if (len <= 0) return 0;
    buf[len] = '\0';
    char *tok = strtok((char*)buf, ",");
    size_t count = 0;
    while (tok && count < max_count) {
        //buffer[count++] = atoi(tok);
        long v = strtol(tok, NULL, 10);
        buffer[count++] = (event_t) v;
        tok = strtok(NULL, ",");
    }
    return count;
}
#else
#include "memory_events.h"
#include <string.h>
static size_t _mem_index = 0;

size_t read_events(event_t *buffer, size_t max_count) {
    if (_mem_index >= memory_events_count) {
        return 0;
    }
    size_t len = memory_events_lengths[_mem_index];
    if (len > max_count) {
        len = max_count;
    }
    memcpy(buffer,
           memory_events[_mem_index],
           len * sizeof(event_t));
    _mem_index++; // = (_mem_index +1) % memory_events_count;
    return len;
}
#endif
