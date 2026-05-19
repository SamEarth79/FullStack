import { useState, memo, useMemo, useCallback } from "react";

// Simulate API data
const POST_DATA = Array.from({ length: 1000 }, (_, i) => ({
  id: i,
  title: `Post ${i}`,
  likes: Math.floor(Math.random() * 100),
}));

// Expensive — filters + sorts 1000 posts
function filterPosts(posts: typeof POST_DATA, filter: string) {
  console.log("filterPosts running...");
  return posts
    .filter(p => p.title.includes(filter))
    .sort((a, b) => b.likes - a.likes);
}

const PostList = memo(function PostList({
    posts,
    onLike,
  }: {
    posts: typeof POST_DATA;
    onLike: (id: number) => void;
  }) {
    console.log("PostList rendered");
    return (
      <ul>
        {posts.slice(0, 10).map(p => (
          <li key={p.id}>
            {p.title} — {p.likes} likes
            <button onClick={() => onLike(p.id)}>Like</button>
          </li>
        ))}
      </ul>
    );
  });

  function ProfilePage() {
    const [filter, setFilter] = useState("");
    const [theme, setTheme] = useState("light");
    const [liked, setLiked] = useState<number[]>([]);
  
    const filteredPosts = useMemo(
      () => filterPosts(POST_DATA, filter),
      [filter]
    );
  
    const handleLike = useCallback((id: number) => {
      setLiked(prev => [...prev, id]);
    }, []); // handleLike function's memory ref is stable reference forever
    
    // const handleLike = (id: number) => {
    //   setLiked(prev => [...prev, id]);
    // }
  
    return (
      <div style={{ background: theme === "light" ? "#fff" : "#333", color: theme === "light" ? "#000" : "#fff" }}>
        <h2>Profile Page</h2>
        <p>Liked posts: {liked.length}</p>
  
        <button onClick={() => setTheme(t => t === "light" ? "dark" : "light")}>
          Toggle Theme ({theme})
        </button>
  
        <input
          placeholder="Filter posts..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
  
        <PostList posts={filteredPosts} onLike={handleLike} />
      </div>
    );
  }
  
export default ProfilePage;