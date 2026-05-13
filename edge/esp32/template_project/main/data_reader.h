#ifndef DATA_READER_H
#define DATA_READER_H

#include <stddef.h>
#include <stdint.h>

#include "config.h"
size_t read_events(event_t *buffer, size_t max_count);

#endif
