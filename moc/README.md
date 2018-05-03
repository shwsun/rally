# Rally

## How to calculate number of instances

```
Max amount of VMs: 10 by project (tenant)
```

So `tenants` < `concurency` x `times`


[Quota error while running rally 
 tasks](https://bugs.launchpad.net/rally/+bug/1269549)





## Reference
[api_versions.py](https://github.com/openstack/rally/blob/master/rally/plugins/openstack/context/api_versions.py)

[utils.py](https://github.com/openstack/rally/blob/master/rally/plugins/openstack/scenarios/keystone/utils.py)

[users.py](https://github.com/openstack/rally/blob/master/rally/plugins/openstack/context/keystone/users.py)

