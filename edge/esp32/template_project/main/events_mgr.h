// events_mgr.h

#ifndef EVENTS_MGR_H
#define EVENTS_MGR_H

#include <stdint.h>
#include <stddef.h>

#include "config.h"

#ifndef EVENTS_MGR_TIME_WINDOW
#define EVENTS_MGR_TIME_WINDOW (2 * (OW_MS)) 
#endif

typedef struct {
    uint64_t    time;
    event_t    *data;
    size_t      length;
} events_mgr_entry_t;

typedef struct events_mgr_s events_mgr_t;

events_mgr_t *events_mgr_create(void);

void events_mgr_destroy(events_mgr_t *mgr);

int events_mgr_add(events_mgr_t *mgr, uint64_t time, const event_t *data, size_t length);

event_t *events_mgr_get_at(events_mgr_t *mgr, uint64_t time, size_t *out_length);

event_t *events_mgr_get_range(events_mgr_t *mgr, uint64_t start_time, uint64_t end_time, size_t *out_length);

void events_mgr_cleanup(events_mgr_t *mgr, uint64_t now);

uint32_t events_mgr_fingerprint(const event_t *events, size_t n);

#endif // EVENTS_MGR_H
