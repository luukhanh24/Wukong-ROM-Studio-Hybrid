# Consume permanent build credits when jobs are accepted

Finite build credits have no periodic reset and are consumed idempotently when a valid job receives a durable Job ID, while configured admins may be unlimited. Validation failures consume nothing, synchronous creation or dispatch failures receive an idempotent compensation, and later build failures or cancellations do not refund automatically because runner work and capacity have already been committed; an admin may grant a documented compensating credit.
