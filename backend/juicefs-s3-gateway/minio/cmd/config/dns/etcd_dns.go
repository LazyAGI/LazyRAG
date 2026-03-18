/*
 * MinIO Cloud Storage, (C) 2018,2020 MinIO, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package dns

import (
	"errors"
	"fmt"
	"strings"

	"github.com/coredns/coredns/plugin/etcd/msg"
	"github.com/minio/minio-go/v7/pkg/set"
)

// ErrNoEntriesFound - Indicates no entries were found for the given key (directory)
var ErrNoEntriesFound = errors.New("No entries found for this key")

// ErrDomainMissing - Indicates domain is missing
var ErrDomainMissing = errors.New("domain is missing")

const etcdPathSeparator = "/"

// Close closes the internal etcd client and cannot be used further
func (c *CoreDNS) Close() error {
	return nil
}

// List - Retrieves list of DNS entries for the domain.
func (c *CoreDNS) List() (map[string][]SrvRecord, error) {
	var srvRecords = map[string][]SrvRecord{}
	for _, domainName := range c.domainNames {
		key := msg.Path(fmt.Sprintf("%s.", domainName), c.prefixPath)
		records, err := c.list(key+etcdPathSeparator, true)
		if err != nil {
			return srvRecords, err
		}
		for _, record := range records {
			if record.Key == "" {
				continue
			}
			srvRecords[record.Key] = append(srvRecords[record.Key], record)
		}
	}
	return srvRecords, nil
}

// Get - Retrieves DNS records for a bucket.
func (c *CoreDNS) Get(bucket string) ([]SrvRecord, error) {
	var srvRecords []SrvRecord
	for _, domainName := range c.domainNames {
		key := msg.Path(fmt.Sprintf("%s.%s.", bucket, domainName), c.prefixPath)
		records, err := c.list(key, false)
		if err != nil {
			return nil, err
		}
		// Make sure we have record.Key is empty
		// this can only happen when record.Key
		// has bucket entry with exact prefix
		// match any record.Key which do not
		// match the prefixes we skip them.
		for _, record := range records {
			if record.Key != "" {
				continue
			}
			srvRecords = append(srvRecords, record)
		}
	}
	if len(srvRecords) == 0 {
		return nil, ErrNoEntriesFound
	}
	return srvRecords, nil
}

// msgUnPath converts a etcd path to domainname.
func msgUnPath(s string) string {
	ks := strings.Split(strings.Trim(s, etcdPathSeparator), etcdPathSeparator)
	for i, j := 0, len(ks)-1; i < j; i, j = i+1, j-1 {
		ks[i], ks[j] = ks[j], ks[i]
	}
	return strings.Join(ks, ".")
}

// Retrieves list of entries under the key passed.
// Note that this method fetches entries upto only two levels deep.
func (c *CoreDNS) list(key string, domain bool) ([]SrvRecord, error) {
	return nil, nil
}

// Put - Adds DNS entries into etcd endpoint in CoreDNS etcd message format.
func (c *CoreDNS) Put(bucket string) error {
	c.Delete(bucket) // delete any existing entries.
	return nil
}

// Delete - Removes DNS entries added in Put().
func (c *CoreDNS) Delete(bucket string) error {
	return nil
}

// DeleteRecord - Removes a specific DNS entry
func (c *CoreDNS) DeleteRecord(record SrvRecord) error {
	return nil
}

// String stringer name for this implementation of dns.Store
func (c *CoreDNS) String() string {
	return "etcdDNS"
}

// CoreDNS - represents dns config for coredns server.
type CoreDNS struct {
	domainNames []string
	domainIPs   set.StringSet
	domainPort  string
	prefixPath  string
}

// EtcdOption - functional options pattern style
type EtcdOption func(*CoreDNS)

// DomainNames set a list of domain names used by this CoreDNS
// client setting, note this will fail if set to empty when
// constructor initializes.
func DomainNames(domainNames []string) EtcdOption {
	return func(args *CoreDNS) {
		args.domainNames = domainNames
	}
}

// DomainIPs set a list of custom domain IPs, note this will
// fail if set to empty when constructor initializes.
func DomainIPs(domainIPs set.StringSet) EtcdOption {
	return func(args *CoreDNS) {
		args.domainIPs = domainIPs
	}
}

// DomainPort - is a string version of server port
func DomainPort(domainPort string) EtcdOption {
	return func(args *CoreDNS) {
		args.domainPort = domainPort
	}
}

// CoreDNSPath - custom prefix on etcd to populate DNS
// service records, optional and can be empty.
// if empty then c.prefixPath is used i.e "/skydns"
func CoreDNSPath(prefix string) EtcdOption {
	return func(args *CoreDNS) {
		args.prefixPath = prefix
	}
}
