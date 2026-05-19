import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

type Todo = {
  id: number;
  title: string;
  completed: boolean;
};

// API calls
const fetchTodos = async (): Promise<Todo[]> => {
  const res = await fetch("https://jsonplaceholder.typicode.com/todos?_limit=10");
  if (!res.ok) throw new Error("Failed to fetch");
  return res.json();
};

const toggleTodo = async (todo: Todo): Promise<Todo> => {
  const res = await fetch(`https://jsonplaceholder.typicode.com/todos/${todo.id}`, {
    method: "PUT",
    body: JSON.stringify({ ...todo, completed: !todo.completed }),
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error("Failed to update");
  return res.json();
};

function TodoApp() {
  const queryClient = useQueryClient();

  const { data: todos, isLoading, error } = useQuery({
    queryKey: ["todos"],
    queryFn: fetchTodos,
  });

  const mutation = useMutation({
    mutationFn: toggleTodo,

    // Optimistic update
    onMutate: async (todo) => {
      // Cancel in-flight refetches — don't overwrite optimistic update
      await queryClient.cancelQueries({ queryKey: ["todos"] });

      // Snapshot current state for rollback
      const previous = queryClient.getQueryData<Todo[]>(["todos"]);

      // Optimistically update cache
      queryClient.setQueryData<Todo[]>(["todos"], old =>
        old?.map(t => t.id === todo.id ? { ...t, completed: !t.completed } : t)
      );

      return { previous }; // context for onError
    },

    onError: (err, todo, context) => {
      // Rollback on failure
      queryClient.setQueryData(["todos"], context?.previous);
    },

    onSettled: () => {
      // Sync with server regardless of success/failure
    //   queryClient.invalidateQueries({ queryKey: ["todos"] });
    },
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {(error as Error).message}</div>;

  return (
    <ul>
      {todos?.map(todo => (
        <li
          key={todo.id}
          onClick={() => mutation.mutate(todo)}
          style={{
            cursor: "pointer",
            textDecoration: todo.completed ? "line-through" : "none",
            padding: "8px",
          }}
        >
          {todo.title}
        </li>
      ))}
    </ul>
  );
}

export default TodoApp;