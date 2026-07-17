import { useNavigate } from 'react-router-dom';
import { Card, Space, Typography } from 'antd';
import StockSearchInput from '../../components/StockSearchInput';

export default function StockChoose() {
  const navigate = useNavigate();

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 'calc(100vh - 180px)' }}>
      <Card style={{ width: '100%', maxWidth: 720 }}>
        <Space direction="vertical" size={24} style={{ display: 'flex', textAlign: 'center' }}>
          <div>
            <Typography.Title level={2}>个股分析</Typography.Title>
            <Typography.Paragraph type="secondary">
              输入股票代码、简称、拼音或首字母，快速定位个股并进入分析页面。
            </Typography.Paragraph>
          </div>

          <StockSearchInput
            autoFocus
            limit={12}
            placeholder="输入股票代码、名称或拼音搜索..."
            onSelect={(match) => navigate(`/stock/${match.code}`)}
          />

          <Space direction="vertical" size={4} style={{ color: '#94a3b8' }}>
            <Typography.Text type="secondary">支持股票代码、简称、拼音和首字母搜索</Typography.Text>
            <Typography.Text type="secondary">当存在多个匹配项时，请先从候选列表中选择</Typography.Text>
          </Space>
        </Space>
      </Card>
    </div>
  );
}
