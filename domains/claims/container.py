from lagom import Container

from domains.claims.app_services.claim_app_service import ClaimAppService
from domains.claims.app_services.interfaces.iclaim_app_service import IClaimAppService
from proxies.claims.claim_service_proxy import ClaimServiceProxy
from services.claims.contracts.iclaim_service import IClaimService

container = Container()
container[IClaimService] = ClaimServiceProxy
container[IClaimAppService] = ClaimAppService
