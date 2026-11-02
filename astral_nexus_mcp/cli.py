def main():
    from .server import server
    server.run(transport='stdio')
