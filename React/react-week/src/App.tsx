import { memo, useMemo, useState } from "react";
import ProfilePage from "./ProfilePage";
import TodoApp from "./TodoApp";


const ExpensiveChild = memo(function ExpensiveChild({ 
  name, 
  style 
}: { 
  name: string; 
  style: object 
}) {
  console.log("ExpensiveChild rendered");
  let i = 0;
  while (i < 1000000) i++;
  return <div style={style}>Hello {name}</div>;
});

function App() {

  const [count, setCount] = useState(0);
  const style = useMemo(()=>({ color: "red" }), []);

  return <div>
    {/* <button onClick={() => {setCount(count=>count+1)}}> 
      Count: {count}
    </button>
    <ExpensiveChild name="Alice" style={style}/> */}
    {/* <ProfilePage /> */}
    <TodoApp />
  </div>;
}

export default App;