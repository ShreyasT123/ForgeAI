import unittest
from helius_agent.tools.vfs import LocalDiskBackend, StateBackend, CompositeBackend, StoreBackend
from helius_agent.tools.files import set_backend, write_file, read_file, ls, edit_file, edit_lines

class TestDeepPlanVFS(unittest.TestCase):
    def test_state_backend_isolation(self):
        # Create a state-based backend (simulating a subagent's memory)
        state = {}
        backend = StateBackend(state)
        set_backend(backend)
        
        # Write to state
        write_file.invoke({"path": "/tmp/test.txt", "content": "hello from state"})
        self.assertIn("/tmp/test.txt", state)
        self.assertEqual(state["/tmp/test.txt"], "hello from state")
        
        # Read from state
        res = read_file.invoke({"path": "/tmp/test.txt"})
        self.assertIn("hello from state", res)

    def test_composite_routing(self):
        state = {}
        state_backend = StateBackend(state)
        local_backend = LocalDiskBackend(root_dir="temp", virtual_mode=True)
        
        # Route /memories/ to state, everything else to local disk
        composite = CompositeBackend(default=local_backend, routes={"/memories/": state_backend})
        set_backend(composite)
        
        # Write to memory (should go to state)
        write_file.invoke({"path": "/memories/user.json", "content": '{"name": "helius"}'})
        self.assertIn("/memories/user.json", state)
        
        # Write to workspace (should go to local disk under temp/)
        import os
        import shutil
        if os.path.exists("temp"): shutil.rmtree("temp")
        os.makedirs("temp")
        
        write_file.invoke({"path": "project.md", "content": "# Project"})
        self.assertTrue(os.path.exists("temp/project.md"))
        
        shutil.rmtree("temp")

    def test_store_backend_persistence(self):
        import os
        store_file = "test_persistence_store.json"
        if os.path.exists(store_file): os.remove(store_file)
        
        # Instance 1: Write data
        backend1 = StoreBackend(store_path=store_file)
        backend1.write("/memories/long_term.txt", "persistent data")
        
        # Instance 2: Should find data
        backend2 = StoreBackend(store_path=store_file)
        res = backend2.read("/memories/long_term.txt")
        self.assertIn("persistent data", res)
        
        if os.path.exists(store_file): os.remove(store_file)

if __name__ == "__main__":
    unittest.main()
