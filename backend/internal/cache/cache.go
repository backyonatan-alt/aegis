package cache

import (
	"sync"
	"time"
)

// Cache holds a pre-serialized JSON response in memory.
type Cache struct {
	mu        sync.RWMutex
	data      []byte
	updatedAt time.Time
}

func New() *Cache {
	return &Cache{}
}

// Set stores the pre-serialized JSON bytes.
func (c *Cache) Set(data []byte) {
	c.mu.Lock()
	c.data = make([]byte, len(data))
	copy(c.data, data)
	c.updatedAt = time.Now()
	c.mu.Unlock()
}

// Get returns the cached JSON bytes, or nil if empty.
func (c *Cache) Get() []byte {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.data == nil {
		return nil
	}
	out := make([]byte, len(c.data))
	copy(out, c.data)
	return out
}

// UpdatedAt returns the last time the cache was updated.
func (c *Cache) UpdatedAt() time.Time {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.updatedAt
}
