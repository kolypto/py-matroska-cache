## 0.1.3 (2020-09-11)
* Performance: do not pass strings through json.dumps() but store them as is
* Reliability: removed race condition when invalidating keys
* Bug: fixed a bug with some keys becoming timeless (having a TTL of -1)

## 0.1.2 (2020-09-10)
* Initial release
