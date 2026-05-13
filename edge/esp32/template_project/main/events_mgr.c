#include "events_mgr.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>

struct events_mgr_s {
    struct node {
        events_mgr_entry_t       entry;
        struct node             *next;
    } *head, *tail;
};

events_mgr_t *events_mgr_create(void) {
    events_mgr_t *mgr = malloc(sizeof(*mgr));
    if (!mgr) return NULL;
    mgr->head = mgr->tail = NULL;
    return mgr;
}

void events_mgr_destroy(events_mgr_t *mgr) {
    if (!mgr) return;
    struct node *cur = mgr->head;
    while (cur) {
        struct node *next = cur->next;
        free(cur->entry.data);
        free(cur);
        cur = next;
    }
    free(mgr);
}

int events_mgr_add(events_mgr_t *mgr, uint64_t time, const event_t *data, size_t length) {
    if (!mgr || (length > 0 && !data)) return -1;
    struct node *n = malloc(sizeof(*n));
    if (!n) return -1;
    n->entry.time   = time;
    n->entry.length = length;
    n->entry.data   = length ? malloc(length * sizeof(event_t)) : NULL;
    if (length && !n->entry.data) {
        free(n);
        return -1;
    }
    if (length) {
        memcpy(n->entry.data, data, length * sizeof(event_t));
    }
    n->next = NULL;
    if (!mgr->head) {
        mgr->head = mgr->tail = n;
    } else {
        mgr->tail->next = n;
        mgr->tail = n;
    }
    events_mgr_cleanup(mgr, time);
    return 0;
}

// (3)
#define SCALE_US(x) ((x) * 1000ULL)

void events_mgr_cleanup(events_mgr_t *mgr, uint64_t now) {
    uint64_t threshold = (now > 2 * SCALE_US(OW_MS))
                         ? (now - 2 * SCALE_US(OW_MS))  
                         : 0;
    while (mgr->head && mgr->head->entry.time < threshold) {
        struct node *old = mgr->head;
        mgr->head = old->next;
        free(old->entry.data);
        free(old);
    }
}

event_t *events_mgr_get_at(events_mgr_t *mgr, uint64_t time, size_t *out_length) {
    if (!mgr || !out_length) return NULL;
    *out_length = 0;
    for (struct node *cur = mgr->head; cur; cur = cur->next) {
        if (cur->entry.time == time) {
            size_t len = cur->entry.length;
            *out_length = len;
            if (len == 0) return NULL;
            event_t *copy = malloc(len * sizeof(event_t));
            if (!copy) { *out_length = 0; return NULL; }
            memcpy((void*)copy, cur->entry.data, len * sizeof(event_t));
            return copy;
        }
    }
    return NULL;
}

event_t *events_mgr_get_range(events_mgr_t *mgr, uint64_t start_time, uint64_t end_time, size_t *out_length) {
    if (!mgr || !out_length) return NULL;
    *out_length = 0;
    size_t total = 0;
    for (struct node *cur = mgr->head; cur; cur = cur->next) {
        if (cur->entry.time >= start_time && cur->entry.time <= end_time) {
            total += cur->entry.length;
        }
    }
    if (total == 0) return NULL;
    event_t  *result = malloc(total * sizeof(event_t));
    if (!result) return NULL;
    size_t pos = 0;
    for (struct node *cur = mgr->head; cur; cur = cur->next) {
        if (cur->entry.time >= start_time && cur->entry.time <= end_time) {
            memcpy(&result[pos], cur->entry.data,
                   cur->entry.length * sizeof(event_t));
            pos += cur->entry.length;
        }
    }
    *out_length = total;
    return result;
}

#define FNV_OFFSET_BASIS 2166136261u
#define FNV_PRIME        16777619u

uint32_t events_mgr_fingerprint(const event_t *events, size_t n)
{
    uint32_t h = FNV_OFFSET_BASIS;
    for (size_t i = 0; i < n; ++i) {
        h ^= (uint32_t)(uint8_t)events[i];
        h *= FNV_PRIME;
    }
    return h;
}

