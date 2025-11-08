#!/usr/bin/env python3
"""
Health check script for the Audio Analysis Service
Run this to verify all services are running correctly
"""

import requests
import sys
from typing import Dict

def check_service(url: str, service_name: str) -> Dict:
    """Check if a service is responding"""
    try:
        response = requests.get(url, timeout=10)
        return {
            'name': service_name,
            'url': url,
            'status': '✅ UP' if response.status_code == 200 else f'❌ DOWN ({response.status_code})',
            'response_time': f"{response.elapsed.total_seconds():.2f}s"
        }
    except requests.exceptions.RequestException as e:
        return {
            'name': service_name,
            'url': url,
            'status': '❌ DOWN',
            'error': str(e)
        }

def main():
    """Main health check function"""
    print("🔍 Audio Analysis Service Health Check")
    print("=" * 50)

    # Services to check
    services = [
        {
            'name': 'FastAPI Web Service',
            'url': 'http://localhost:8001/health'
        },
        {
            'name': 'Web Interface',
            'url': 'http://localhost:8001/'
        }
    ]

    results = []
    for service in services:
        print(f"Checking {service['name']}...")
        result = check_service(service['url'], service['name'])
        results.append(result)

        status = result['status']
        if 'error' in result:
            status += f" - {result['error']}"

        print(f"  {status}")
        if 'response_time' in result:
            print(f"  Response time: {result['response_time']}")
        print()

    # Summary
    print("📊 Summary:")
    healthy_services = sum(1 for r in results if '✅ UP' in r['status'])
    total_services = len(results)

    if healthy_services == total_services:
        print(f"✅ All {total_services} services are healthy!")
        return 0
    else:
        print(f"⚠️  {healthy_services}/{total_services} services are healthy")
        return 1

if __name__ == "__main__":
    sys.exit(main())
